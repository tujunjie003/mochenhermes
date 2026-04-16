#!/usr/bin/env python3
"""
飞书告警集成模块

功能：
1. 任务失败告警
2. 任务超时告警
3. 定时健康报告
4. 告警频率限制（避免轰炸）
"""

import json
import time
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import urllib.request
import urllib.error


# 飞书Webhook地址
FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/fab854d9-6920-4861-9c33-53a1ccc13de4"

# 告警级别
ALERT_LEVEL = {
    "INFO": {"emoji": "ℹ️", "color": "绿色"},
    "WARN": {"emoji": "⚠️", "color": "橙色"},
    "ERROR": {"emoji": "❌", "color": "红色"},
    "CRITICAL": {"emoji": "🚨", "color": "红色"},
}


class FeishuAlert:
    """飞书告警器"""

    # 告警冷却时间（秒）— 同一个任务告警间隔
    COOLDOWN_SECONDS = 300  # 5分钟

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = Path.home() / ".hermes" / "remes" / "mochenhermes"
        self.base_dir = Path(base_dir)
        self.alerts_dir = self.base_dir / "logs" / "alerts"
        self.alerts_dir.mkdir(parents=True, exist_ok=True)
        self.webhook_url = FEISHU_WEBHOOK_URL

    def _save_alert_record(self, task_id: str, alert_type: str) -> None:
        """记录告警历史（用于频率限制）"""
        record_file = self.alerts_dir / f"{task_id}_{alert_type}.json"
        record = {
            "task_id": task_id,
            "alert_type": alert_type,
            "timestamp": datetime.now().isoformat(),
            "count": 1
        }

        # 如果已存在记录，增加计数
        if record_file.exists():
            try:
                with open(record_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                record["count"] = existing.get("count", 0) + 1
            except Exception:
                pass

        with open(record_file, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

    def _can_alert(self, task_id: str, alert_type: str) -> bool:
        """检查是否可以发送告警（频率限制）"""
        record_file = self.alerts_dir / f"{task_id}_{alert_type}.json"

        if not record_file.exists():
            return True

        try:
            with open(record_file, 'r', encoding='utf-8') as f:
                record = json.load(f)

            last_alert_time = datetime.fromisoformat(record["timestamp"])
            elapsed = (datetime.now() - last_alert_time).total_seconds()

            return elapsed >= self.COOLDOWN_SECONDS
        except Exception:
            return True

    def _send_message(self, content: dict) -> bool:
        """发送消息到飞书"""
        try:
            data = json.dumps(content, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))

                if result.get("code") == 0 or result.get("StatusCode") == 0:
                    return True
                else:
                    print(f"飞书API错误: {result}")
                    return False

        except urllib.error.URLError as e:
            print(f"飞书请求失败: {e}")
            return False
        except Exception as e:
            print(f"飞书发送异常: {e}")
            return False

    def send_task_failed(
        self,
        task_id: str,
        error: str,
        retry_count: int = 0,
        max_retries: int = 3
    ) -> bool:
        """
        发送任务失败告警

        Args:
            task_id: 任务ID
            error: 错误信息
            retry_count: 当前重试次数
            max_retries: 最大重试次数
        """
        # 频率限制
        if not self._can_alert(task_id, "failed"):
            print(f"告警冷却中，跳过: {task_id}")
            return False

        self._save_alert_record(task_id, "failed")

        # 判断是否已达最大重试
        if retry_count < max_retries:
            level = "WARN"
            title = "⚠️ 任务执行异常（将自动重试）"
        else:
            level = "ERROR"
            title = "❌ 任务执行失败（已停止）"

        content = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": "red" if level == "ERROR" else "orange"
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "tag": "lark_md",
                                "content": f"**任务ID**\n{task_id}"
                            },
                            {
                                "tag": "lark_md",
                                "content": f"**重试情况**\n{retry_count}/{max_retries}"
                            }
                        ]
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**错误信息**\n```\n{error[:500]}\n```"
                        }
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "note",
                        "fields": [
                            {
                                "tag": "plain_text",
                                "content": f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            }
                        ]
                    }
                ]
            }
        }

        return self._send_message(content)

    def send_task_timeout(self, task_id: str, estimated_time: int, actual_time: float) -> bool:
        """发送任务超时告警"""
        if not self._can_alert(task_id, "timeout"):
            return False

        self._save_alert_record(task_id, "timeout")

        content = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "⏰ 任务超时告警"
                    },
                    "template": "orange"
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "tag": "lark_md",
                                "content": f"**任务ID**\n{task_id}"
                            },
                            {
                                "tag": "lark_md",
                                "content": f"**预估时间**\n{estimated_time}秒"
                            }
                        ]
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "tag": "lark_md",
                                "content": f"**实际耗时**\n{actual_time:.0f}秒"
                            },
                            {
                                "tag": "lark_md",
                                "content": f"**超时幅度**\n+{actual_time - estimated_time:.0f}秒"
                            }
                        ]
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "note",
                        "fields": [
                            {
                                "tag": "plain_text",
                                "content": f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            }
                        ]
                    }
                ]
            }
        }

        return self._send_message(content)

    def send_health_report(
        self,
        stats: dict,
        recent_failed: list
    ) -> bool:
        """发送健康报告（定时任务）"""
        content = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "📊 Hermes 系统健康报告"
                    },
                    "template": "green"
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "tag": "lark_md",
                                "content": f"**总任务数**\n{stats.get('total', 0)}"
                            },
                            {
                                "tag": "lark_md",
                                "content": f"**完成率**\n{stats.get('completed', 0)}/{stats.get('total', 0)}"
                            }
                        ]
                    },
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "tag": "lark_md",
                                "content": f"**待执行**\n{stats.get('pending', 0)}"
                            },
                            {
                                "tag": "lark_md",
                                "content": f"**失败任务**\n{stats.get('failed', 0)}"
                            }
                        ]
                    },
                ]
            }
        }

        # 如果有失败任务，添加到报告中
        if recent_failed:
            failed_list = "\n".join([
                f"- {f['task_id']}: {f['error'][:50]}..." 
                for f in recent_failed[:5]
            ])
            content["card"]["elements"].append({"tag": "hr"})
            content["card"]["elements"].append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**最近失败任务**\n{failed_list}"
                }
            })

        # 添加时间
        content["card"]["elements"].append({"tag": "hr"})
        content["card"]["elements"].append({
            "tag": "note",
            "fields": [
                {
                    "tag": "plain_text",
                    "content": f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        })

        return self._send_message(content)

    def send_simple_message(
        self,
        message: str,
        level: str = "INFO"
    ) -> bool:
        """发送简单文本消息"""
        emoji = ALERT_LEVEL.get(level, {}).get("emoji", "ℹ️")

        content = {
            "msg_type": "text",
            "content": {
                "text": f"{emoji} {message}"
            }
        }

        return self._send_message(content)


def test_alert():
    """测试告警功能"""
    alert = FeishuAlert()

    print("1. 测试简单消息...")
    result = alert.send_simple_message("Hermes 测试消息 - 这是一条简单通知", "INFO")
    print(f"   结果: {'成功' if result else '失败'}")

    time.sleep(1)

    print("2. 测试失败告警...")
    result = alert.send_task_failed(
        task_id="test_task_001",
        error="文件读取失败: permission denied",
        retry_count=2,
        max_retries=3
    )
    print(f"   结果: {'成功' if result else '失败'}")

    time.sleep(1)

    print("3. 测试超时告警...")
    result = alert.send_task_timeout(
        task_id="test_task_002",
        estimated_time=300,
        actual_time=450
    )
    print(f"   结果: {'成功' if result else '失败'}")

    time.sleep(1)

    print("4. 测试健康报告...")
    stats = {
        "total": 10,
        "pending": 2,
        "running": 1,
        "completed": 6,
        "failed": 1
    }
    recent_failed = [
        {"task_id": "task_001", "error": "超时"},
        {"task_id": "task_002", "error": "文件不存在"}
    ]
    result = alert.send_health_report(stats, recent_failed)
    print(f"   结果: {'成功' if result else '失败'}")


if __name__ == "__main__":
    test_alert()
