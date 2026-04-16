#!/usr/bin/env python3
"""
考研学习提醒脚本
根据当天是周几发送对应的学习提醒
"""

import sys
from datetime import datetime

# 添加scripts路径
sys.path.insert(0, '/home/hermes/.hermes/repos/mochenhermes/scripts')

try:
    from feishu_alert import FeishuAlert
    base_dir = '/home/hermes/.hermes/repos/mochenhermes'
    feishu = FeishuAlert(base_dir)
except Exception as e:
    print(f"导入失败: {e}")
    sys.exit(1)


def send_reminder():
    """发送当日学习提醒"""
    weekday = datetime.now().weekday()  # 0=周一, 6=周日
    
    reminders = {
        # 周一（0）- 休息日
        0: {
            "title": "📚 考研学习提醒 - 周一（休息日）",
            "items": [
                "08:00 健身",
                "09:00-12:00 数学（3小时）",
                "14:00-18:00 408（4小时）",
                "19:00-22:00 英语（3小时）",
                "22:00-23:00 政治（1小时）",
            ]
        },
        # 周二（1）
        1: {
            "title": "📚 考研学习提醒 - 周二",
            "items": [
                "08:00 健身",
                "09:00-12:00 数学（3小时）",
                "21:30-24:00 数学/408/英语（2.5小时）",
            ]
        },
        # 周三（2）
        2: {
            "title": "📚 考研学习提醒 - 周三",
            "items": [
                "08:00 健身",
                "09:00-12:00 数学（3小时）",
                "21:30-24:00 数学/408/英语（2.5小时）",
            ]
        },
        # 周四（3）
        3: {
            "title": "📚 考研学习提醒 - 周四",
            "items": [
                "08:00 健身",
                "09:00-12:00 数学（3小时）",
                "21:30-24:00 数学/408/英语（2.5小时）",
            ]
        },
        # 周五（4）
        4: {
            "title": "📚 考研学习提醒 - 周五",
            "items": [
                "08:00 健身",
                "09:00-12:00 数学（3小时）",
                "21:30-24:00 数学/408/英语（2.5小时）",
            ]
        },
        # 周六（5）
        5: {
            "title": "📚 考研学习提醒 - 周六",
            "items": [
                "09:00-21:30 上班",
                "22:30-24:00 英语+政治（1.5小时）",
            ]
        },
        # 周日（6）
        6: {
            "title": "📚 考研学习提醒 - 周日",
            "items": [
                "09:00-18:30 上班",
                "19:30-24:00 数学+408（4.5小时）",
            ]
        },
    }
    
    reminder = reminders.get(weekday)
    if not reminder:
        return False
    
    # 构建消息
    items_text = "\n".join([f"• {item}" for item in reminder["items"]])
    
    content = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": reminder["title"]},
                "template": "blue"
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": items_text}},
                {"tag": "hr"},
                {"tag": "note", "fields": [
                    {"tag": "plain_text", "content": f"💪 加油！还剩247天"}
                ]}
            ]
        }
    }
    
    return feishu._send_message(content)


if __name__ == "__main__":
    success = send_reminder()
    print("发送成功" if success else "发送失败")
    sys.exit(0 if success else 1)
