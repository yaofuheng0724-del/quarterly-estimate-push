#!/bin/bash
set -e

SKILL_DIR="$HOME/.claude/skills/quarterly-estimate-push"
PLIST_NAME="com.chaitin.quarterly-estimate-push"
PLIST_SRC="$SKILL_DIR/com.chaitin.quarterly-estimate-push.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "=== 季度预估签约数据对比推送 - 安装脚本 ==="
echo ""

# 1. 创建目录结构
echo "[1/7] 创建目录结构..."
mkdir -p "$SKILL_DIR"/{scripts,snapshots,logs}

# 2. 创建 config.json（如不存在）
if [ ! -f "$SKILL_DIR/config.json" ]; then
    echo "[2/7] 从模板创建 config.json..."
    cp "$SKILL_DIR/config.example.json" "$SKILL_DIR/config.json"
    echo "  ⚠️  请编辑 config.json 填写 crm_group_id"
else
    echo "[2/7] config.json 已存在，跳过"
fi

# 3. 设置脚本可执行权限
echo "[3/7] 设置脚本权限..."
chmod +x "$SKILL_DIR/scripts/run.sh"

# 4. 安装 launchd plist
echo "[4/7] 安装 launchd plist..."
# 替换 plist 中的用户目录占位符
if [ -f "$PLIST_SRC" ]; then
    # 动态生成 plist，使用当前用户 HOME 和 config 中的 push_time
    # 读取 push_time 配置
    PUSH_TIME=$(python3 -c "import json; c=json.load(open('$SKILL_DIR/config.json')); print(c.get('push_time','08:40'))")
    PUSH_HOUR=$(echo "$PUSH_TIME" | cut -d: -f1)
    PUSH_MINUTE=$(echo "$PUSH_TIME" | cut -d: -f2)
    # pmset 唤醒时间比推送时间早5分钟
    WAKE_MINUTE=$(printf "%02d" $((10#$PUSH_MINUTE - 5 >= 0 ? 10#$PUSH_MINUTE - 5 : 55)))
    WAKE_HOUR=$(printf "%02d" $((10#$PUSH_MINUTE - 5 >= 0 ? 10#$PUSH_HOUR : 10#$PUSH_HOUR - 1)))

    cat > "$PLIST_DST" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SKILL_DIR/scripts/run.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>$PUSH_HOUR</integer>
        <key>Minute</key><integer>$PUSH_MINUTE</integer>
    </dict>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>$HOME</string>
    </dict>
    <key>StandardOutPath</key>
    <string>$SKILL_DIR/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$SKILL_DIR/logs/stderr.log</string>
</dict>
</plist>
PLISTEOF
    echo "  plist 已安装到 $PLIST_DST (推送时间: $PUSH_TIME)"
else
    echo "  ⚠️  plist 源文件不存在: $PLIST_SRC"
fi

# 5. 加载 launchd
echo "[5/7] 加载 launchd..."
if launchctl list | grep -q "$PLIST_NAME"; then
    echo "  已加载，先卸载..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi
launchctl load "$PLIST_DST"
echo "  launchd 已加载"

# 6. 设置 pmset 唤醒
echo "[6/7] 设置 pmset 每日唤醒 (${WAKE_HOUR}:${WAKE_MINUTE})..."
echo "  需要管理员权限："
sudo pmset repeat wake MTWRFSU ${WAKE_HOUR}:${WAKE_MINUTE}:00 || {
    echo "  ⚠️  pmset 设置失败，电脑休眠时可能无法自动唤醒"
    echo "  你可以手动运行: sudo pmset repeat wake MTWRFSU ${WAKE_HOUR}:${WAKE_MINUTE}:00"
}

# 7. 完成
echo ""
echo "[7/7] 安装完成！"
echo ""
echo "下一步："
echo "  1. 编辑配置: vim $SKILL_DIR/config.json"
echo "     - 填写 crm_group_id（金融头部战队和战略伙伴战队的组ID）"
echo "     - 确认 dingtalk_group_ids 正确"
echo "  2. 认证 DWS: dws auth login"
echo "  3. 测试运行: claude -p '执行 quarterly-estimate-push skill'"
echo "  4. 查看日志: tail -f $SKILL_DIR/logs/stdout.log"
echo ""
echo "卸载: bash $SKILL_DIR/scripts/uninstall.sh"
