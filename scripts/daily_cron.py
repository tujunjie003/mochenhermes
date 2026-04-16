#!/usr/bin/env python3
"""
每日定时任务脚本
每天早9点 + 晚9点自动执行

执行内容:
1. 备忘录提醒检查 → 飞书通知
2. 新闻抓取 → 飞书推送
3. 执行日志记录

完整闭环:
触发 → 执行 → 记录日志 → 异常告警 → 完成
"""

import sys
import json
from datetime import datetime
from pathlib import Path

# 添加scripts路径
sys.path.insert(0, str(Path(__file__).parent))


def log(msg: str):
    """打印日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def main():
    log("=" * 50)
    log("每日定时任务开始执行")
    log("=" * 50)

    base_dir = Path.home() / ".hermes" / "repos" / "mochenhermes"

    # ========== 1. 备忘录提醒检查 ==========
    log("步骤1: 检查备忘录提醒...")
    try:
        from memo_manager import MemoManager
        memo_mgr = MemoManager()

        # 发送到期提醒
        reminded_count = memo_mgr.send_reminders()
        log(f"备忘录提醒: 发送了 {reminded_count} 条")

        # 获取今日待办
        today_report = memo_mgr.format_today_report()
        log(f"今日待办:\n{today_report}")

    except Exception as e:
        log(f"备忘录处理出错: {e}")

    log("-" * 50)

    # ========== 2. 新闻抓取推送 ==========
    log("步骤2: 抓取新闻...")
    try:
        from news_monitor import NewsMonitor
        news_mgr = NewsMonitor(base_dir)

        # 抓取所有分类
        results = news_mgr.fetch_all()

        # 统计
        total = sum(len(v) for v in results.values())
        log(f"新闻抓取完成: 共 {total} 条")
        for cat, items in results.items():
            log(f"  - {cat}: {len(items)} 条")

        # 推送到飞书
        if total > 0:
            pushed = news_mgr.push_to_feishu(results)
            log(f"新闻推送: {'成功' if pushed else '失败或已推送'}")

    except Exception as e:
        log(f"新闻处理出错: {e}")

    log("-" * 50)

    # ========== 3. 系统健康检查 ==========
    log("步骤3: 系统健康检查...")
    try:
        from task_monitor import TaskMonitor
        monitor = TaskMonitor(base_dir)

        # 发送健康报告
        sent = monitor.send_health_report()
        log(f"健康报告: {'已发送' if sent else '发送失败'}")

    except Exception as e:
        log(f"健康检查出错: {e}")

    log("-" * 50)

    # ========== 完成 ==========
    log("每日定时任务执行完成")
    log("=" * 50)

    # 返回状态（用于判断是否需要告警）
    return 0


if __name__ == "__main__":
    exit(main())
