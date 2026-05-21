#!/bin/bash
set -e

SKILL_DIR="$HOME/.claude/skills/quarterly-estimate-push"
PLIST_NAME="com.chaitin.quarterly-estimate-push"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "=== 季度预估签约数据对比推送 - 卸载脚本 ==="
echo ""

# 1. 卸载 launchd
echo "[1/3] 卸载 launchd..."
if launchctl list | grep -q "$PLIST_NAME"; then
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    echo "  launchd 已卸载"
else
    echo "  launchd 未加载，跳过"
fi

# 2. 移除 plist
echo "[2/3] 移除 plist 文件..."
if [ -f "$PLIST_DST" ]; then
    rm "$PLIST_DST"
    echo "  plist 已移除"
else
    echo "  plist 文件不存在，跳过"
fi

# 3. 询问是否删除数据
echo "[3/3] 清理数据..."
read -p "是否删除快照和日志文件？(y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$SKILL_DIR/snapshots"/*
    rm -rf "$SKILL_DIR/logs"/*
    echo "  快照和日志已清除"
else
    echo "  保留快照和日志"
fi

echo ""
echo "卸载完成。"
echo "如需完全删除 Skill，运行: rm -rf $SKILL_DIR"
