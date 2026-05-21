---
name: quarterly-estimate-push
description: 自动推送季度预估签约数据对比到钉钉群。每个工作日自动运行，比较项目金额、业绩核算时间、项目承诺的变化，并推送到指定战队钉钉群。
---

# 季度预估签约数据对比推送

执行此 Skill 时，严格按照以下步骤顺序执行。每一步都必须完成后再进入下一步。

## 前置条件

- CRM MCP 服务器已连接且可用
- DWS CLI 已认证（`dws auth status` 正常）
- `config.json` 中的 `crm_group_id` 已正确填写

## 执行步骤

### Step 1: 工作日检查

```bash
python3 ~/.claude/skills/quarterly-estimate-push/scripts/snapshot_manager.py is-workday
```

如果退出码非0（非工作日），直接输出"今日非工作日，跳过推送"并结束。

### Step 2: 读取配置

读取 `~/.claude/skills/quarterly-estimate-push/config.json`，提取：
- 每个战队的 `crm_group_id` 和 `dingtalk_group_ids`
- `excluded_stages`
- `snapshot_dir`

### Step 3: 计算当前季度范围

运行以下命令获取当前季度信息（或直接在 Skill 中计算）：

- 当前季度：根据今天日期计算，Q1=1-3月，Q2=4-6月，Q3=7-9月，Q4=10-12月
- 季初日期和季末日期

### Step 4: 获取 CRM 数据

对 config.json 中的每个战队，执行以下查询：

**4.1 查询项目列表**

使用 `mcp__crm__crm_query_project` 的 `list` action：

```json
{
  "action": "list",
  "search": {
    "claim_by_group": "<crm_group_id>",
    "deal_date": { "from": "<季初>", "to": "<季末>" }
  },
  "pagination": { "skip": 0, "limit": 200 }
}
```

注意：不在此处排除 stage，因为需要获取完整列表后再做快照对比。但排除 stage 为 `invalid` 和 `lost_order` 的项目。

**4.2 获取项目详情**

对列表中的每个项目，使用 `mcp__crm__crm_query_project` 的 `detail` action 获取完整信息（包括 `deal_amount` 和 `project_promise`）：

```json
{
  "action": "detail",
  "id": "<project_id>"
}
```

**4.3 获取应收计划**

对列表中的每个项目，使用 `mcp__crm__crm_contract_finance` 的 `income_plan` domain 的 `query` action：

```json
{
  "domain": "income_plan",
  "action": "query",
  "params": { "project_id": "<project_id>" }
}
```

提取：
- `assessment_date`：业绩核算时间
- `money.value`：金额
- `revenue_with_overdue_data`：非空表示已核算

### Step 5: 构建今日快照

将收集的项目数据按以下 JSON 格式组织，通过 stdin 传给 Python 脚本：

```bash
echo '<项目数据JSON>' | python3 ~/.claude/skills/quarterly-estimate-push/scripts/snapshot_manager.py build-snapshot
```

输入格式：
```json
{
  "金融头部战队": [
    {
      "id": "xxx",
      "name": "项目名称",
      "stage": "business_tender",
      "owner_name": "负责人",
      "company_name": "客户名",
      "deal_amount": "300000.00",
      "project_promise": "must_sign",
      "income_plans": [
        {
          "assessment_date": "2026-06-28T16:00:00Z",
          "money": { "value": "99000.00" },
          "revenue_with_overdue_data": []
        }
      ],
      "updated_at": "2026-05-19T15:12:56.649Z"
    }
  ]
}
```

脚本的输出即为今日快照 JSON。保存到临时文件（如 `/tmp/qep_current_snapshot.json`）。

### Step 6: 查找最新快照

```bash
python3 ~/.claude/skills/quarterly-estimate-push/scripts/snapshot_manager.py find-latest-snapshot
```

- 如果找到，输出文件路径
- 如果当天已有快照（早上自动运行生成的），手动执行时会对比当天早上的快照，检测日间变化
- 如果未找到（首次运行），所有项目将自动归入"新增项目"区块

### Step 7: 对比快照

如果有最新快照：

```bash
python3 ~/.claude/skills/quarterly-estimate-push/scripts/snapshot_manager.py compare \
  --previous <最新快照路径> \
  --current /tmp/qep_current_snapshot.json
```

对比逻辑：
- **早上自动运行**: 最新快照是昨天的 → 对比昨日与今日的变化
- **当天手动运行**: 最新快照是今天的（早上自动生成的）→ 对比今早与当前的变化，消息标题会标注"手动刷新"

如果无最新快照（首次运行），手动构建一个所有项目归入 `newly_added` 的 diff JSON。

### Step 8: 格式化钉钉消息

```bash
echo '<diff JSON>' | python3 ~/.claude/skills/quarterly-estimate-push/scripts/snapshot_manager.py format-message
```

输出格式为 `{ "金融头部战队": "消息内容...", "战略伙伴战队": "消息内容..." }`。

### Step 9: 发送钉钉消息

对每个战队，将其消息发送到所有绑定的钉钉群：

```bash
dws chat message send \
  --group "<dingtalk_group_id>" \
  --title "季度预估签约数据日报 YYYY-MM-DD" \
  --text "<消息内容>" \
  --format json
```

每个战队的 `dingtalk_group_ids` 数组中的所有群都要发送。

如果消息超过 18000 字符，拆分为多条消息发送。

### Step 10: 保存今日快照

```bash
cat /tmp/qep_current_snapshot.json | python3 ~/.claude/skills/quarterly-estimate-push/scripts/snapshot_manager.py save-snapshot
```

### Step 11: 清理临时文件

```bash
rm -f /tmp/qep_current_snapshot.json
```

## 错误处理

- **CRM API 失败**: 重试 1 次，仍失败则通过钉钉推送"CRM 数据获取失败"通知
- **DWS 认证过期**: 日志记录错误，输出"DWS 认证过期，请重新运行 dws auth login"
- **无历史快照**: 正常处理，所有项目归入"新增项目"
- **空对比结果**: 仍然推送消息，显示"今日无数据变动"
