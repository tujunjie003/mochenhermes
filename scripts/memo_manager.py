#!/usr/bin/env python3
"""
备忘录管理器 (Memo Manager)
工作+生活助理的记忆核心

完整闭环:
- 增: 记事情/想法/灵感
- 查: 搜索/筛选/按标签
- 改: 更新内容/状态
- 删: 删除(软删除+归档)
- 提醒: 设置提醒时间+飞书通知
- 完成: 标记完成+归档
- 统计: 今日/本周/汇总

存储结构:
notes/
├── index.json        # 索引(快速搜索)
├── archive/          # 归档(已完成/删除)
│   ├── 2024/
│   └── ...
├── backup/           # 每日备份
└── memos/            # 备忘录文件
    ├── 工作.md
    ├── 生活.md
    ├── 待办.md
    └── 灵感.md

状态流转:
pending → in_progress → completed
                    ↘ cancelled → archived
"""

import json
import re
import hashlib
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict


@dataclass
class Memo:
    """备忘录条目"""
    id: str              # 唯一ID (hash)
    content: str         # 内容
    category: str        # 分类: 工作/生活/待办/灵感
    tags: List[str]      # 标签
    status: str          # pending/in_progress/completed/cancelled
    created_at: str      # 创建时间
    updated_at: str      # 更新时间
    reminded_at: str     # 提醒时间 (空=不提醒)
    completed_at: str    # 完成时间 (空=未完成)
    source: str          # 来源: user/system

    def to_dict(self):
        return asdict(self)


class MemoManager:
    """备忘录管理器"""

    CATEGORIES = ["工作", "生活", "待办", "灵感"]

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = Path.home() / ".hermes" / "repos" / "mochenhermes"
        self.base_dir = Path(base_dir)
        self.notes_dir = self.base_dir / "notes"
        self.memos_dir = self.notes_dir / "memos"
        self.archive_dir = self.notes_dir / "archive"
        self.backup_dir = self.notes_dir / "backup"
        self.index_file = self.notes_dir / "index.json"

        # 创建目录结构
        for d in [self.notes_dir, self.memos_dir, self.archive_dir, self.backup_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 初始化索引
        if not self.index_file.exists():
            self._save_index({"memos": [], "last_backup": None})

    # ========== 核心操作 ==========

    def add(
        self,
        content: str,
        category: str = "待办",
        tags: List[str] = None,
        reminded_at: str = None,
        source: str = "user"
    ) -> Memo:
        """新增备忘录"""
        now = datetime.now().isoformat()
        memo_id = self._generate_id(content, now)

        memo = Memo(
            id=memo_id,
            content=content.strip(),
            category=category if category in self.CATEGORIES else "待办",
            tags=tags or self._extract_tags(content),
            status="pending",
            created_at=now,
            updated_at=now,
            reminded_at=reminded_at or "",
            completed_at="",
            source=source
        )

        # 保存到索引
        index = self._load_index()
        index["memos"].append(memo.to_dict())
        self._save_index(index)

        # 同时追加到分类文件
        self._append_to_category_file(memo)

        return memo

    def get(self, memo_id: str) -> Optional[Memo]:
        """获取单个备忘录"""
        index = self._load_index()
        for m in index["memos"]:
            if m["id"] == memo_id:
                return Memo(**m)
        return None

    def search(
        self,
        query: str = None,
        category: str = None,
        tags: List[str] = None,
        status: str = None,
        limit: int = 50
    ) -> List[Memo]:
        """搜索备忘录"""
        index = self._load_index()
        results = []

        for m in index["memos"]:
            # 状态过滤
            if status and m["status"] != status:
                continue

            # 分类过滤
            if category and m["category"] != category:
                continue

            # 标签过滤
            if tags:
                if not any(t in m["tags"] for t in tags):
                    continue

            # 关键词搜索
            if query:
                q = query.lower()
                if q not in m["content"].lower() and q not in " ".join(m["tags"]).lower():
                    continue

            results.append(Memo(**m))

        # 按时间倒序
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[:limit]

    def update(
        self,
        memo_id: str,
        content: str = None,
        category: str = None,
        tags: List[str] = None,
        status: str = None,
        reminded_at: str = None
    ) -> Optional[Memo]:
        """更新备忘录"""
        index = self._load_index()

        for i, m in enumerate(index["memos"]):
            if m["id"] == memo_id:
                now = datetime.now().isoformat()

                if content is not None:
                    m["content"] = content.strip()
                if category is not None:
                    m["category"] = category
                if tags is not None:
                    m["tags"] = tags
                if status is not None:
                    m["status"] = status
                    if status == "completed":
                        m["completed_at"] = now
                if reminded_at is not None:
                    m["reminded_at"] = reminded_at

                m["updated_at"] = now

                self._save_index(index)
                return Memo(**m)

        return None

    def delete(self, memo_id: str, hard: bool = False) -> bool:
        """删除备忘录"""
        index = self._load_index()

        for i, m in enumerate(index["memos"]):
            if m["id"] == memo_id:
                if hard:
                    # 硬删除
                    index["memos"].pop(i)
                else:
                    # 软删除 -> 归档
                    m["status"] = "cancelled"
                    m["updated_at"] = datetime.now().isoformat()
                    self._archive_memo(Memo(**m))
                    index["memos"].pop(i)

                self._save_index(index)
                return True

        return False

    def complete(self, memo_id: str) -> Optional[Memo]:
        """标记完成"""
        return self.update(memo_id, status="completed")

    def archive_old(self, days: int = 30) -> int:
        """归档旧备忘录"""
        index = self._load_index()
        archived = 0
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        remaining = []
        for m in index["memos"]:
            if m["status"] in ["completed", "cancelled"]:
                if m["updated_at"] < cutoff:
                    self._archive_memo(Memo(**m))
                    archived += 1
                else:
                    remaining.append(m)
            else:
                remaining.append(m)

        index["memos"] = remaining
        self._save_index(index)
        return archived

    # ========== 提醒功能 ==========

    def get_due_memos(self) -> List[Memo]:
        """获取到期的备忘录（用于提醒）"""
        index = self._load_index()
        now = datetime.now()
        due = []

        for m in index["memos"]:
            if m["status"] not in ["pending", "in_progress"]:
                continue
            if not m["reminded_at"]:
                continue

            try:
                reminded = datetime.fromisoformat(m["reminded_at"])
                if reminded <= now:
                    due.append(Memo(**m))
            except Exception:
                continue

        return due

    def send_reminders(self) -> int:
        """发送到期提醒到飞书，返回发送数量"""
        due_memos = self.get_due_memos()
        if not due_memos:
            return 0

        try:
            from feishu_alert import FeishuAlert
            feishu = FeishuAlert(self.base_dir)

            # 格式化提醒
            if len(due_memos) == 1:
                m = due_memos[0]
                title = f"📌 提醒: {m.content[:30]}..."
                fields = [
                    {"tag": "lark_md", "content": f"**内容**\n{m.content}"},
                    {"tag": "lark_md", "content": f"**分类**\n{m.category}"},
                ]
            else:
                title = f"📋 您有 {len(due_memos)} 项待办提醒"
                items = "\n".join([f"• {m.content[:40]}..." for m in due_memos])
                fields = [
                    {"tag": "lark_md", "content": f"**待办事项**\n{items}"}
                ]

            content = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": title},
                        "template": "red"
                    },
                    "elements": [
                        {"tag": "div", "fields": fields},
                        {"tag": "hr"},
                        {"tag": "note", "fields": [
                            {"tag": "plain_text", "content": f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                        ]}
                    ]
                }
            }

            # 发送
            import urllib.request
            data = json.dumps(content, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                feishu.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
                if result.get("code") == 0 or result.get("StatusCode") == 0:
                    # 标记已提醒（更新提醒时间避免重复）
                    for m in due_memos:
                        next_time = datetime.now() + timedelta(hours=1)
                        self.update(m.id, reminded_at=next_time.isoformat())
                    return len(due_memos)

        except Exception as e:
            print(f"发送提醒失败: {e}")

        return 0

    def get_today_memos(self) -> Dict[str, List[Memo]]:
        """获取今日备忘录"""
        today = datetime.now().date().isoformat()
        index = self._load_index()

        today_memos = []
        for m in index["memos"]:
            if m["created_at"].startswith(today) and m["status"] == "pending":
                today_memos.append(Memo(**m))

        # 按分类分组
        grouped = {cat: [] for cat in self.CATEGORIES}
        for memo in today_memos:
            grouped[memo.category].append(memo)

        return grouped

    # ========== 统计功能 ==========

    def get_statistics(self) -> Dict:
        """获取统计数据"""
        index = self._load_index()
        stats = {
            "total": len(index["memos"]),
            "by_status": {},
            "by_category": {},
            "by_source": {},
            "pending_count": 0,
            "completed_today": 0,
            "overdue_count": 0
        }

        now = datetime.now()
        today = now.date().isoformat()

        for m in index["memos"]:
            # 状态统计
            status = m["status"]
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

            # 分类统计
            cat = m["category"]
            stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1

            # 来源统计
            src = m["source"]
            stats["by_source"][src] = stats["by_source"].get(src, 0) + 1

            # 待办数
            if status in ["pending", "in_progress"]:
                stats["pending_count"] += 1

            # 今日完成
            if m["status"] == "completed" and m.get("completed_at", "").startswith(today):
                stats["completed_today"] += 1

            # 逾期数
            if m["status"] == "pending" and m["reminded_at"]:
                try:
                    reminded = datetime.fromisoformat(m["reminded_at"])
                    if reminded < now:
                        stats["overdue_count"] += 1
                except Exception:
                    pass

        return stats

    # ========== 备份功能 ==========

    def backup(self) -> str:
        """创建备份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"backup_{timestamp}.json"

        index = self._load_index()
        index["last_backup"] = datetime.now().isoformat()

        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

        # 只保留最近10个备份
        backups = sorted(self.backup_dir.glob("backup_*.json"), reverse=True)
        for old in backups[10:]:
            old.unlink()

        return str(backup_file)

    # ========== 私有方法 ==========

    def _generate_id(self, content: str, timestamp: str) -> str:
        """生成唯一ID"""
        data = f"{content}{timestamp}"
        return hashlib.md5(data.encode()).hexdigest()[:12]

    def _extract_tags(self, content: str) -> List[str]:
        """从内容中提取标签"""
        # 匹配 #标签
        tags = re.findall(r'#(\w+)', content)
        return list(set(tags))[:5]  # 最多5个

    def _load_index(self) -> Dict:
        """加载索引"""
        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"memos": [], "last_backup": None}

    def _save_index(self, index: Dict) -> None:
        """保存索引"""
        # 先写临时文件，再原子替换
        temp_file = self.index_file.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        temp_file.replace(self.index_file)

    def _append_to_category_file(self, memo: Memo) -> None:
        """追加到分类文件"""
        category_files = {
            "工作": self.memos_dir / "工作.md",
            "生活": self.memos_dir / "生活.md",
            "待办": self.memos_dir / "待办.md",
            "灵感": self.memos_dir / "灵感.md"
        }

        file_path = category_files.get(memo.category)
        if not file_path:
            return

        # 追加格式
        entry = f"""
---
- **时间**: {memo.created_at}
- **状态**: {memo.status}
- **标签**: {', '.join(f'#{t}' for t in memo.tags) if memo.tags else '无'}
- **提醒**: {memo.reminded_at or '无'}

{memo.content}
"""
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(entry)

    def _archive_memo(self, memo: Memo) -> None:
        """归档备忘录"""
        year = datetime.now().strftime("%Y")
        archive_year_dir = self.archive_dir / year
        archive_year_dir.mkdir(exist_ok=True)

        archive_file = archive_year_dir / f"{memo.id}.json"
        with open(archive_file, 'w', encoding='utf-8') as f:
            json.dump(memo.to_dict(), f, ensure_ascii=False, indent=2)

    # ========== 格式化输出 ==========

    def format_memo_list(self, memos: List[Memo], show_stats: bool = False) -> str:
        """格式化备忘录列表"""
        if not memos:
            return "（空）"

        lines = []
        for i, m in enumerate(memos, 1):
            status_icon = {
                "pending": "⏳",
                "in_progress": "🔄",
                "completed": "✅",
                "cancelled": "❌"
            }.get(m.status, "❓")

            lines.append(f"{i}. {status_icon} {m.content}")
            lines.append(f"   分类:{m.category} | 创建:{m.created_at[:10]}")

            if m.tags:
                lines.append(f"   标签: {' '.join(f'#{t}' for t in m.tags)}")

            if m.reminded_at:
                lines.append(f"   提醒: {m.reminded_at[:16]}")

            lines.append("")

        if show_stats:
            stats = self.get_statistics()
            lines.append(f"📊 总数:{stats['total']} | 待办:{stats['pending_count']} | 今日完成:{stats['completed_today']}")

        return "\n".join(lines)

    def format_today_report(self) -> str:
        """格式化今日报告"""
        grouped = self.get_today_memos()
        stats = self.get_statistics()

        lines = [
            f"📋 今日待办 ({datetime.now().strftime('%Y-%m-%d')})",
            f"今日新增: {sum(len(v) for v in grouped.values())} | 待完成: {stats['pending_count']} | 逾期: {stats['overdue_count']}",
            ""
        ]

        for cat in self.CATEGORIES:
            memos = grouped[cat]
            if memos:
                lines.append(f"【{cat}】")
                for m in memos:
                    lines.append(f"  • {m.content}")
                lines.append("")

        return "\n".join(lines)


def main():
    """命令行测试"""
    manager = MemoManager()

    import sys
    if len(sys.argv) < 2:
        print("用法:")
        print("  python memo_manager.py add <内容> [-c category] [-t tag1,tag2]")
        print("  python memo_manager.py list [category]")
        print("  python memo_manager.py search <关键词>")
        print("  python memo_manager.py complete <id>")
        print("  python memo_manager.py stats")
        print("  python memo_manager.py today")
        return

    cmd = sys.argv[1]

    if cmd == "add":
        content = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if content:
            memo = manager.add(content)
            print(f"已添加: {memo.id}")
        else:
            print("请提供内容")

    elif cmd == "list":
        category = sys.argv[2] if len(sys.argv) > 2 else None
        memos = manager.search(category=category) if category else manager.search()
        print(manager.format_memo_list(memos, show_stats=True))

    elif cmd == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if query:
            memos = manager.search(query=query)
            print(manager.format_memo_list(memos))
        else:
            print("请提供搜索词")

    elif cmd == "complete":
        if len(sys.argv) > 2:
            memo_id = sys.argv[2]
            result = manager.complete(memo_id)
            print(f"已标记完成: {result.id if result else '未找到'}")

    elif cmd == "stats":
        stats = manager.get_statistics()
        print(f"📊 统计:")
        print(f"  总数: {stats['total']}")
        print(f"  待办: {stats['pending_count']}")
        print(f"  今日完成: {stats['completed_today']}")
        print(f"  逾期: {stats['overdue_count']}")

    elif cmd == "today":
        print(manager.format_today_report())

    else:
        print(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()
