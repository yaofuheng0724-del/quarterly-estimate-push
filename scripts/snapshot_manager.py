#!/usr/bin/env python3
"""Snapshot manager for quarterly estimate push.

Subcommands:
  is-workday              Check if today is a workday (exit 0=yes, 1=no)
  build-snapshot          Read project data from stdin, output snapshot JSON
  compare                 Compare two snapshots, output diff JSON
  format-message          Read diff JSON from stdin, output DingTalk markdown
  save-snapshot           Read snapshot JSON from stdin, save to file
  find-latest-snapshot     Print the path of the most recent snapshot (includes today)
"""

import sys
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def load_config():
    config_path = SKILL_DIR / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    # Expand ~ in snapshot_dir
    config["snapshot_dir"] = os.path.expanduser(config.get("snapshot_dir", str(SKILL_DIR / "snapshots")))
    return config


# ─── Quarter helpers ───

def get_current_quarter_range():
    today = date.today()
    quarter = (today.month - 1) // 3 + 1
    q_start = date(today.year, (quarter - 1) * 3 + 1, 1)
    if quarter == 4:
        q_end = date(today.year, 12, 31)
    else:
        next_q_start = date(today.year, quarter * 3 + 1, 1)
        q_end = next_q_start - timedelta(days=1)
    return q_start, q_end, quarter


def date_in_quarter(dt_str, q_start, q_end):
    """Check if an ISO date string falls within [q_start, q_end]."""
    if not dt_str:
        return False
    try:
        # Handle "2026-06-28T16:00:00Z" format
        d = date.fromisoformat(dt_str[:10])
        return q_start <= d <= q_end
    except (ValueError, IndexError):
        return False


# ─── Workday helpers ───

def is_workday(target_date=None):
    target = target_date or date.today()
    config = load_config()
    year_str = str(target.year)
    holidays_config = config.get("chinese_holidays", {}).get(year_str, {})
    holidays = set(holidays_config.get("holidays", []))
    workday_overrides = set(holidays_config.get("workday_overrides", []))
    date_str = target.isoformat()

    if target.weekday() >= 5:
        return date_str in workday_overrides
    return date_str not in holidays


def find_latest_snapshot():
    """Find the most recent snapshot file, including today's.

    If today's snapshot exists (from morning auto-run), return it so manual
    re-runs compare against the morning baseline. Otherwise search backwards
    for the previous workday's snapshot.
    """
    config = load_config()
    snapshot_dir = Path(config["snapshot_dir"])
    today = date.today()

    # Check today first (manual re-run scenario)
    today_file = snapshot_dir / f"snapshot_{today.isoformat()}.json"
    if today_file.exists():
        return str(today_file)

    # Search up to 10 days back
    for i in range(1, 11):
        d = today - timedelta(days=i)
        snapshot_file = snapshot_dir / f"snapshot_{d.isoformat()}.json"
        if snapshot_file.exists():
            return str(snapshot_file)
    return None


# ─── Promise mapping ───

PROMISE_MAP = {
    "must_sign": "必签",
    "focus_strive_for": "重点争取",
    "strive_for": "争取",
    "take_part_in": "参与",
}


def promise_display(val):
    if val is None:
        return "-"
    return PROMISE_MAP.get(val, val)


# ─── Amount formatting ───

def format_amount(val):
    """Format amount string to 'XX万' if >= 10000, else raw."""
    if not val or val == "0.00":
        return "0"
    try:
        num = float(val)
        if num >= 10000:
            return f"{num / 10000:.2f}万"
        return f"{num:.2f}"
    except (ValueError, TypeError):
        return str(val)


def format_date(dt_str):
    """Format ISO datetime to YYYY-MM-DD."""
    if not dt_str:
        return "-"
    try:
        return dt_str[:10]
    except (IndexError, TypeError):
        return str(dt_str)


# ─── Subcommand: is-workday ───

def cmd_is_workday():
    sys.exit(0 if is_workday() else 1)


# ─── Subcommand: build-snapshot ───

def cmd_build_snapshot():
    """Read project data JSON from stdin, build and output snapshot JSON.

    Expected stdin format:
    {
      "team_name": [
        {
          "id": "...",
          "name": "...",
          "stage": "...",
          "owner_name": "...",
          "company_name": "...",
          "deal_amount": "300000.00",
          "project_promise": "must_sign",
          "income_plans": [
            {
              "assessment_date": "2026-06-28T16:00:00Z",
              "money": "99000.00",
              "revenue_with_overdue_data": []
            }
          ]
        }
      ]
    }
    """
    data = json.load(sys.stdin)
    q_start, q_end, quarter = get_current_quarter_range()

    snapshot = {
        "date": date.today().isoformat(),
        "quarter": quarter,
        "quarter_start": q_start.isoformat(),
        "quarter_end": q_end.isoformat(),
        "teams": {}
    }

    for team_name, projects in data.items():
        team_projects = {}
        for p in projects:
            # Find the relevant income_plan for this quarter
            relevant_plans = []
            for plan in p.get("income_plans", []):
                ad = plan.get("assessment_date", "")
                if date_in_quarter(ad, q_start, q_end):
                    relevant_plans.append(plan)

            if not relevant_plans:
                continue  # Skip projects with no income_plan in current quarter

            # Use the nearest assessment_date as accounting_date
            nearest_plan = min(relevant_plans,
                               key=lambda pl: abs(date.fromisoformat(pl["assessment_date"][:10]).toordinal() - date.today().toordinal()))

            # Determine accounting_status
            all_settled = all(len(plan.get("revenue_with_overdue_data", [])) > 0 for plan in relevant_plans)
            accounting_status = "已核算" if all_settled else "未核算"

            # Skip projects where accounting_status is "已核算"
            if accounting_status == "已核算":
                continue

            # Performance amount: sum of money for plans in this quarter
            perf_amount = sum(float(plan.get("money", {}).get("value", 0)) for plan in relevant_plans)

            team_projects[p["id"]] = {
                "name": p.get("name", ""),
                "stage": p.get("stage", ""),
                "owner_name": p.get("owner_name", ""),
                "company_name": p.get("company_name", ""),
                "deal_amount": p.get("deal_amount", "0.00"),
                "project_promise": p.get("project_promise"),
                "accounting_date": format_date(nearest_plan.get("assessment_date", "")),
                "accounting_status": accounting_status,
                "performance_amount": f"{perf_amount:.2f}",
                "updated_at": p.get("updated_at", "")
            }

        snapshot["teams"][team_name] = {"projects": team_projects}

    json.dump(snapshot, sys.stdout, ensure_ascii=False, indent=2)


# ─── Subcommand: compare ───

def cmd_compare(previous_path, current_path):
    with open(previous_path, "r", encoding="utf-8") as f:
        prev = json.load(f)
    with open(current_path, "r", encoding="utf-8") as f:
        curr = json.load(f)

    diff = {"date": curr["date"], "teams": {}}

    # Detect same-day re-run (manual execution after morning auto-run)
    prev_date = prev.get("date", "")
    is_same_day = prev_date == curr["date"]
    if is_same_day:
        diff["baseline_note"] = f"对比基准：今日 {prev_date} 早上快照（手动刷新）"

    for team_name in curr.get("teams", {}):
        curr_projects = curr["teams"][team_name]["projects"]
        prev_projects = prev.get("teams", {}).get(team_name, {}).get("projects", {})

        amount_changes = []
        date_changes = []
        promise_changes = []
        newly_settled = []
        newly_added = []

        for pid, cp in curr_projects.items():
            if pid not in prev_projects:
                newly_added.append({
                    "name": cp["name"],
                    "owner_name": cp["owner_name"],
                    "deal_amount": cp["deal_amount"],
                    "accounting_date": cp["accounting_date"],
                })
                continue

            pp = prev_projects[pid]

            # Amount change
            if cp["deal_amount"] != pp["deal_amount"]:
                amount_changes.append({
                    "name": cp["name"],
                    "owner_name": cp["owner_name"],
                    "project_promise": cp["project_promise"],
                    "accounting_date": cp["accounting_date"],
                    "old_amount": pp["deal_amount"],
                    "new_amount": cp["deal_amount"],
                })

            # Accounting date change
            if cp["accounting_date"] != pp["accounting_date"]:
                date_changes.append({
                    "name": cp["name"],
                    "owner_name": cp["owner_name"],
                    "project_promise": cp["project_promise"],
                    "deal_amount": cp["deal_amount"],
                    "old_date": pp["accounting_date"],
                    "new_date": cp["accounting_date"],
                })

            # Promise change
            if (cp["project_promise"] is not None and pp["project_promise"] is not None
                    and cp["project_promise"] != pp["project_promise"]):
                promise_changes.append({
                    "name": cp["name"],
                    "owner_name": cp["owner_name"],
                    "deal_amount": cp["deal_amount"],
                    "accounting_date": cp["accounting_date"],
                    "old_promise": pp["project_promise"],
                    "new_promise": cp["project_promise"],
                })

            # Newly settled
            if pp["accounting_status"] == "未核算" and cp["accounting_status"] == "已核算":
                newly_settled.append({
                    "name": cp["name"],
                    "owner_name": cp["owner_name"],
                    "performance_amount": cp["performance_amount"],
                })

        diff["teams"][team_name] = {
            "amount_changes": amount_changes,
            "date_changes": date_changes,
            "promise_changes": promise_changes,
            "newly_settled": newly_settled,
            "newly_added": newly_added,
        }

    json.dump(diff, sys.stdout, ensure_ascii=False, indent=2)


# ─── Subcommand: format-message ───

def _red(text):
    return f'<font color="red">{text}</font>'


def cmd_format_message():
    diff = json.load(sys.stdin)
    config = load_config()
    empty_text = config.get("message_settings", {}).get("empty_section_text", "本项无变动")

    messages = {}

    for team_name, team_diff in diff.get("teams", {}).items():
        lines = []
        report_date = diff["date"]
        lines.append(f"## 季度预估签约数据日报 {report_date}（{team_name}）")
        # Show baseline note for same-day re-runs
        baseline_note = diff.get("baseline_note")
        if baseline_note:
            lines.append(f"\n> {baseline_note}")
        lines.append("")

        # Section 1: Amount changes
        lines.append("### 一、项目金额变动")
        lines.append("")
        ac = team_diff["amount_changes"]
        if ac:
            lines.append("| 项目名称 | 负责人 | 项目承诺 | 业绩核算日期 | 调整前金额 | 调整后金额 |")
            lines.append("|---------|--------|---------|------------|-----------|-----------|")
            for item in ac:
                lines.append(f"| {item['name']} | {item['owner_name']} | {promise_display(item['project_promise'])} | {item['accounting_date']} | {_red(format_amount(item['old_amount']))} | {_red(format_amount(item['new_amount']))} |")
        else:
            lines.append(empty_text)
        lines.append("")

        # Section 2: Accounting date changes
        lines.append("### 二、业绩核算时间变动")
        lines.append("")
        dc = team_diff["date_changes"]
        if dc:
            lines.append("| 项目名称 | 负责人 | 项目承诺 | 项目金额 | 调整前核算时间 | 调整后核算时间 |")
            lines.append("|---------|--------|---------|---------|-------------|-------------|")
            for item in dc:
                lines.append(f"| {item['name']} | {item['owner_name']} | {promise_display(item['project_promise'])} | {format_amount(item['deal_amount'])} | {_red(item['old_date'])} | {_red(item['new_date'])} |")
        else:
            lines.append(empty_text)
        lines.append("")

        # Section 3: Promise changes
        lines.append("### 三、项目承诺变动")
        lines.append("")
        pc = team_diff["promise_changes"]
        if pc:
            lines.append("| 项目名称 | 负责人 | 项目金额 | 业绩核算时间 | 调整前承诺 | 调整后承诺 |")
            lines.append("|---------|--------|---------|------------|-----------|-----------|")
            for item in pc:
                lines.append(f"| {item['name']} | {item['owner_name']} | {format_amount(item['deal_amount'])} | {item['accounting_date']} | {_red(promise_display(item['old_promise']))} | {_red(promise_display(item['new_promise']))} |")
        else:
            lines.append(empty_text)
        lines.append("")

        # Section 4: Newly settled
        lines.append("### 四、新结算项目")
        lines.append("")
        ns = team_diff["newly_settled"]
        if ns:
            lines.append("| 项目名称 | 负责人 | 项目绩效金额 |")
            lines.append("|---------|--------|------------|")
            for item in ns:
                lines.append(f"| {item['name']} | {item['owner_name']} | {format_amount(item['performance_amount'])} |")
        else:
            lines.append(empty_text)
        lines.append("")

        # Section 5: Newly added
        lines.append("### 五、新增项目")
        lines.append("")
        na = team_diff["newly_added"]
        if na:
            lines.append("| 项目名称 | 负责人 | 合同签单金额 | 业绩核算时间 |")
            lines.append("|---------|--------|------------|------------|")
            for item in na:
                lines.append(f"| {item['name']} | {item['owner_name']} | {format_amount(item['deal_amount'])} | {item['accounting_date']} |")
        else:
            lines.append(empty_text)
        lines.append("")

        lines.append("> 数据来源：CRM系统 | 自动推送")

        messages[team_name] = "\n".join(lines)

    json.dump(messages, sys.stdout, ensure_ascii=False, indent=2)


# ─── Subcommand: save-snapshot ───

def cmd_save_snapshot():
    snapshot = json.load(sys.stdin)
    config = load_config()
    snapshot_dir = Path(config["snapshot_dir"])
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_date = snapshot.get("date", date.today().isoformat())
    filepath = snapshot_dir / f"snapshot_{snapshot_date}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"Snapshot saved to {filepath}")

    # Cleanup: keep only last 30 days of snapshots
    _cleanup_old_snapshots(snapshot_dir, 30)


def _cleanup_old_snapshots(snapshot_dir, keep_days):
    cutoff = date.today() - timedelta(days=keep_days)
    for f in snapshot_dir.glob("snapshot_*.json"):
        try:
            d = date.fromisoformat(f.stem.replace("snapshot_", ""))
            if d < cutoff:
                f.unlink()
        except ValueError:
            pass


# ─── Subcommand: find-latest-snapshot ───

def cmd_find_latest_snapshot():
    result = find_latest_snapshot()
    if result:
        print(result)
    else:
        sys.exit(1)


# ─── Main ───

def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "is-workday":
        cmd_is_workday()
    elif cmd == "build-snapshot":
        cmd_build_snapshot()
    elif cmd == "compare":
        if len(sys.argv) < 4:
            print("Usage: snapshot_manager.py compare --previous <path> --current <path>", file=sys.stderr)
            sys.exit(1)
        prev_path = sys.argv[sys.argv.index("--previous") + 1]
        curr_path = sys.argv[sys.argv.index("--current") + 1]
        cmd_compare(prev_path, curr_path)
    elif cmd == "format-message":
        cmd_format_message()
    elif cmd == "save-snapshot":
        cmd_save_snapshot()
    elif cmd == "find-latest-snapshot":
        cmd_find_latest_snapshot()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
