# 季度预估签约数据对比 - 钉钉自动推送

自动获取 CRM 系统中季度预估签单数据，每日对比变化（金额、业绩核算时间、项目承诺），通过钉钉群组推送变更信息。

## 功能概述

- 每个工作日早上 08:40 自动推送
- 按战队（金融头部战队、战略伙伴战队）分别推送
- 五类变更检测：金额变动、核算时间变动、承诺变动、新结算项目、新增项目
- 变动值红色高亮显示
- 合盖休眠状态下自动唤醒运行

## 快速开始

### 前置条件

- macOS 系统
- Claude Code CLI 已安装
- CRM MCP 服务器已配置
- DWS CLI 已安装并认证

### 安装

```bash
cd ~/.claude/skills/quarterly-estimate-push
bash scripts/setup.sh
```

安装脚本会：
1. 创建目录结构
2. 生成 config.json（从模板）
3. 安装 launchd 定时任务
4. 设置 pmset 每日唤醒

### 配置

编辑 `~/.claude/skills/quarterly-estimate-push/config.json`：

```json
{
  "teams": [
    {
      "name": "金融头部战队",
      "crm_group_id": "<填写CRM战队组ID>",
      "dingtalk_group_ids": ["cidT7sSBbTvyRRCINcqosUizg=="]
    },
    {
      "name": "战略伙伴战队",
      "crm_group_id": "<填写CRM战队组ID>",
      "dingtalk_group_ids": ["cidVICTgRHlL4lAgpl1jnJKEA=="]
    }
  ]
}
```

**必填字段**：
- `crm_group_id`：CRM 系统中的战队组 ID（MongoDB ObjectId 格式），用于筛选项目
- `dingtalk_group_ids`：钉钉群 openConversationId 数组，支持一个战队绑定多个群

### 认证 DWS

```bash
dws auth login
```

扫码认证后即可发送钉钉消息。刷新令牌 30 天有效，每日自动运行会自动续期。

### 测试

```bash
claude -p "执行 quarterly-estimate-push skill"
```

## 配置参考

### config.json 完整字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | number | 配置版本号，当前为 1 |
| `teams` | array | 战队配置列表 |
| `teams[].name` | string | 战队名称，用于消息标题显示 |
| `teams[].crm_group_id` | string | CRM 战队组 ID，用于 claim_by_group 筛选 |
| `teams[].dingtalk_group_ids` | string[] | 钉钉群 ID 数组，一条消息推送到所有绑定的群 |
| `excluded_stages` | string[] | 排除的项目阶段，默认排除 invalid 和 lost_order |
| `push_time` | string | 每日推送时间，格式 "HH:MM"，默认 "08:40" |
| `snapshot_dir` | string | 快照存储目录，支持 ~ 路径 |
| `chinese_holidays` | object | 中国节假日配置，按年份组织 |
| `chinese_holidays.<year>.holidays` | string[] | 法定节假日日期列表（YYYY-MM-DD） |
| `chinese_holidays.<year>.workday_overrides` | string[] | 调休工作日列表（周末补班的日期） |
| `message_settings.title_template` | string | 消息标题模板，`{date}` 替换为日期 |
| `message_settings.empty_section_text` | string | 无变动时显示的文字 |

### 项目承诺枚举映射

| CRM 值 | 显示名称 |
|--------|---------|
| must_sign | 必签 |
| focus_strive_for | 重点争取 |
| strive_for | 争取 |
| take_part_in | 参与 |

## 消息格式

每日推送消息包含五个区块：

### 一、项目金额变动
对比字段：合同签单金额（deal_amount）

| 项目名称 | 负责人 | 项目承诺 | 业绩核算日期 | 调整前金额 | 调整后金额 |
|---------|--------|---------|------------|-----------|-----------|

变动金额用红色高亮显示。

### 二、业绩核算时间变动
对比字段：业绩核算时间（assessment_date）

| 项目名称 | 负责人 | 项目承诺 | 项目金额 | 调整前核算时间 | 调整后核算时间 |
|---------|--------|---------|---------|-------------|-------------|

变动日期用红色高亮显示。

### 三、项目承诺变动
对比字段：项目承诺（project_promise）

| 项目名称 | 负责人 | 项目金额 | 业绩核算时间 | 调整前承诺 | 调整后承诺 |
|---------|--------|---------|------------|-----------|-----------|

变动承诺用红色高亮显示。

### 四、新结算项目
前一天业绩核算状态从"未核算"变为"已核算"的项目。

| 项目名称 | 负责人 | 项目绩效金额 |
|---------|--------|------------|

### 五、新增项目
前一天快照中没有，但今天新增进来的项目。

| 项目名称 | 负责人 | 合同签单金额 | 业绩核算时间 |
|---------|--------|------------|------------|

## 项目筛选规则

1. 项目负责人归属于配置中的战队
2. 排除业绩核算状态为"已核算"的项目
3. 排除项目阶段为"失效"（invalid）或"丢单"（lost_order）的项目
4. 项目的业绩核算时间（income_plan.assessment_date）在当前季度内

季度范围自动计算：
- Q1: 1月1日 - 3月31日
- Q2: 4月1日 - 6月30日
- Q3: 7月1日 - 9月30日
- Q4: 10月1日 - 12月31日

## 定时调度

### 工作机制

推送时间由 config.json 中的 `push_time` 控制（默认 "08:40"），运行 setup.sh 时自动设置到 launchd 和 pmset。

```
push_time-5min  pmset 唤醒电脑
push_time       launchd 触发 run.sh
                ├─ is-workday 检查（非工作日退出）
                ├─ DWS 认证检查
                └─ claude -p 执行 Skill
```

### 修改推送时间

1. 编辑 config.json 中的 `push_time`（如改为 "09:00"）
2. 重新运行 `bash scripts/setup.sh`（会自动更新 launchd 和 pmset）

### 手动执行

```bash
# 方式1：通过 Skill 手动运行（推荐，支持日间对比）
claude -p "执行 quarterly-estimate-push skill"

# 方式2：通过 launchctl 触发
launchctl start com.chaitin.quarterly-estimate-push
```

**日间手动执行行为**：如果当天早上已经自动运行过（存在当天快照），手动执行时会：
- 对比当天早上的快照与当前 CRM 数据
- 检测早上推送后发生的变化
- 消息中标注"对比基准：今日 YYYY-MM-DD 早上快照（手动刷新）"
- 执行后更新当天快照，下次手动执行对比此次数据

# 查看加载状态
launchctl list | grep quarterly

# 查看日志
tail -f ~/.claude/skills/quarterly-estimate-push/logs/stdout.log
```

## 关闭与卸载

### 临时暂停（保留配置，停止自动推送）

```bash
# 1. 停止 launchd 定时任务（不再自动触发）
launchctl unload ~/Library/LaunchAgents/com.chaitin.quarterly-estimate-push.plist

# 2. 取消 pmset 每日唤醒
sudo pmset repeat cancel
```

恢复运行：
```bash
launchctl load ~/Library/LaunchAgents/com.chaitin.quarterly-estimate-push.plist
sudo pmset repeat wake MTWRFSU 08:35:00   # 时间需与 config.json 中 push_time 对应
```

或直接重新运行 `bash scripts/setup.sh`，会自动恢复。

### 完整卸载（删除定时任务和数据）

```bash
bash ~/.claude/skills/quarterly-estimate-push/scripts/uninstall.sh
```

卸载脚本会：
1. 停止并卸载 launchd 定时任务
2. 删除 plist 文件
3. 询问是否删除快照和日志数据

### 彻底删除（包括 Skill 本身）

```bash
# 1. 先运行卸载脚本
bash ~/.claude/skills/quarterly-estimate-push/scripts/uninstall.sh

# 2. 删除 Skill 目录
rm -rf ~/.claude/skills/quarterly-estimate-push

# 3. 取消 pmset 唤醒（卸载脚本不包含此步骤）
sudo pmset repeat cancel

# 4. 确认 launchd 已清理
launchctl list | grep quarterly   # 应无输出
ls ~/Library/LaunchAgents/ | grep quarterly   # 应无文件
```

## 可移植性

将整个项目目录拷贝到同事电脑，按以下步骤操作：

1. 拷贝 `~/.claude/skills/quarterly-estimate-push/` 目录
2. 运行 `bash scripts/setup.sh`
3. 编辑 `config.json`，修改：
   - `crm_group_id`：改为该同事负责的战队组 ID
   - `dingtalk_group_ids`：改为目标钉钉群 ID
4. 运行 `dws auth login` 扫码认证
5. 测试运行 `claude -p "执行 quarterly-estimate-push skill"`

### 多人共用

同一台电脑上不需要安装多个实例。修改 `config.json` 的 `teams` 数组即可：
- 增加战队：添加新的 team 对象
- 增加推送群：在 `dingtalk_group_ids` 数组中添加更多群 ID
- 一对多绑定：一个 `crm_group_id` 可绑定多个钉钉群

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| CRM API 失败 | 重试 1 次，仍失败推送"CRM 数据获取失败"通知 |
| DWS 认证过期 | 日志记录，需重新运行 `dws auth login` |
| 首次运行（无快照） | 所有项目归入"新增项目"区块 |
| 快照文件损坏 | 自动重命名为 .corrupt，视为无快照 |
| 消息超过 18000 字符 | 自动拆分为多条消息 |
| 今日无变动 | 推送"今日无数据变动" |

## 节假日维护

每年初需要更新 `config.json` 中的 `chinese_holidays` 部分。添加新年份的节假日和调休日。

参考：国务院办公厅关于当年部分节假日安排的通知。

## 文件结构

```
~/.claude/skills/quarterly-estimate-push/
├── SKILL.md                    # Skill 指令文件
├── README.md                   # 说明文档
├── config.json                 # 配置文件
├── config.example.json         # 配置模板
├── scripts/
│   ├── snapshot_manager.py     # 快照管理、对比、格式化
│   ├── run.sh                  # launchd 调用入口
│   ├── setup.sh                # 安装脚本
│   └── uninstall.sh            # 卸载脚本
├── snapshots/                  # 每日快照（自动生成）
├── logs/                       # 运行日志（自动生成）
└── com.chaitin.quarterly-estimate-push.plist  # launchd 配置模板
```

## 常见问题

**Q: 电脑合盖休眠时能自动推送吗？**
A: 可以。setup.sh 会根据 config.json 中的 `push_time` 设置 pmset 提前5分钟唤醒电脑，到点自动执行推送。需要 sudo 权限。

**Q: DWS 认证多久过期？**
A: 刷新令牌 30 天有效，但每次使用会自动续期。每日自动运行时令牌会持续有效。超过 30 天未使用才需要重新认证。

**Q: 如何添加新的战队？**
A: 在 config.json 的 teams 数组中添加新的对象，填写 name、crm_group_id 和 dingtalk_group_ids。

**Q: 如何修改推送时间？**
A: 编辑 config.json 中的 `push_time`（如 "09:00"），然后重新运行 `bash scripts/setup.sh`，会自动更新 launchd 和 pmset 配置。

**Q: 手动执行时对比的是哪天的数据？**
A: 如果当天早上已自动运行过（存在当天快照），手动执行会对比当天早上的快照，检测日间变化。如果是当天首次运行，则对比前一工作日的快照。消息中会标注对比基准。

**Q: 快照数据保留多久？**
A: 自动保留最近 30 天的快照，更早的自动清理。
