#!/bin/bash
set -e

SKILL_DIR="$HOME/.claude/skills/quarterly-estimate-push"
cd "$SKILL_DIR"

# 工作日检查（非工作日静默退出）
python3 scripts/snapshot_manager.py is-workday || exit 0

# 检查 DWS 认证状态
if ! dws auth status --format json > /dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') DWS not authenticated" >> logs/stderr.log
    exit 1
fi

# 执行 Skill
claude -p \
  --dangerously-skip-permissions \
  "执行 quarterly-estimate-push skill：获取今日 CRM 数据，与昨日快照对比，推送差异到钉钉群组" \
  >> logs/stdout.log 2>> logs/stderr.log
