#!/usr/bin/env python3
"""
技能管理器 (Skill Manager)
技能沉淀系统核心组件

功能：
1. 技能创建（从任务经验中提取）
2. 技能搜索（按关键词/类型）
3. 技能加载（获取完整技能信息）
4. 技能自动沉淀（任务完成后自动总结）
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict


@dataclass
class Skill:
    """技能定义"""
    name: str
    description: str
    category: str  # devops, data-science, mlops, etc.
    trigger_keywords: list  # 触发关键词
    steps: list  # 执行步骤
    tools_used: list  # 使用的工具
    pitfalls: list  # 注意事项
    verification: str  # 验证方法
    examples: list  # 使用示例
    created_at: str
    updated_at: str
    times_used: int = 0

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "trigger_keywords": self.trigger_keywords,
            "steps": self.steps,
            "tools_used": self.tools_used,
            "pitfalls": self.pitfalls,
            "verification": self.verification,
            "examples": self.examples,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "times_used": self.times_used
        }


class SkillManager:
    """技能管理器"""

    SKILL_CATEGORIES = [
        "devops", "data-science", "mlops", "software-development",
        "research", "productivity", "social-media", "media",
        "gaming", "email", "note-taking", "smart-home", "mcp"
    ]

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = Path.home() / ".hermes" / "repos" / "mochenhermes"
        self.base_dir = Path(base_dir)
        self.skills_dir = self.base_dir / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # 每个category一个子目录
        for cat in self.SKILL_CATEGORIES:
            (self.skills_dir / cat).mkdir(exist_ok=True)

    def _sanitize_name(self, name: str) -> str:
        """将技能名转换为合法的目录名"""
        # 转为小写，替换空格和特殊字符为下划线
        name = name.lower().strip()
        name = re.sub(r'[^\w\u4e00-\u9fff-]', '_', name)  # 保留中文、字母、数字、下划线、连字符
        name = re.sub(r'_+', '_', name)  # 多个下划线合并
        return name.strip('_')

    def _extract_category(self, skill_data: dict, forced_category: str = None) -> str:
        """提取或推断分类"""
        if forced_category and forced_category in self.SKILL_CATEGORIES:
            return forced_category

        # 从描述中推断
        desc = skill_data.get("description", "").lower()
        name = skill_data.get("name", "").lower()

        keywords_map = {
            "devops": ["deploy", "docker", "k8s", "ci/cd", "git", "github", "pipeline", "自动化", "部署", "运维"],
            "data-science": ["data", "jupyter", "分析", "pandas", "numpy", "统计", "可视化"],
            "mlops": ["model", "training", "fine-tune", "gpu", "llm", "训练", "模型", "机器学习"],
            "software-development": ["code", "debug", "test", "refactor", "代码", "调试", "测试", "重构"],
            "research": ["paper", "arxiv", "论文", "研究", "学术"],
            "productivity": ["document", "pdf", "ppt", "spreadsheet", "文档", "效率"],
            "social-media": ["twitter", "x.com", "post", "tweet", "社交", "发帖"],
            "media": ["video", "audio", "youtube", "视频", "音频", "音乐"],
            "gaming": ["game", "minecraft", "游戏"],
            "email": ["email", "mail", "邮件"],
            "note-taking": ["note", "obsidian", "笔记", "记录"],
            "smart-home": ["home", "hue", "light", "智能家居", "灯"],
            "mcp": ["mcp", "model context protocol", "server"]
        }

        text = desc + " " + name
        for cat, keywords in keywords_map.items():
            if any(kw in text for kw in keywords):
                return cat

        return "software-development"  # 默认分类

    def create_skill(
        self,
        name: str,
        description: str,
        steps: list,
        tools_used: list = None,
        pitfalls: list = None,
        verification: str = None,
        examples: list = None,
        category: str = None,
        trigger_keywords: list = None
    ) -> str:
        """
        创建新技能

        Returns: 技能存储路径
        """
        category = self._extract_category(
            {"description": description, "name": name},
            category
        )

        skill_dir = self.skills_dir / category / self._sanitize_name(name)

        # 如果已存在，添加版本号
        if skill_dir.exists():
            base_name = self._sanitize_name(name)
            counter = 1
            while (self.skills_dir / category / f"{base_name}_{counter}").exists():
                counter += 1
            skill_dir = self.skills_dir / category / f"{base_name}_{counter}"

        skill_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat()

        skill = Skill(
            name=name,
            description=description,
            category=category,
            trigger_keywords=trigger_keywords or self._extract_keywords(description),
            steps=steps,
            tools_used=tools_used or [],
            pitfalls=pitfalls or [],
            verification=verification or "",
            examples=examples or [],
            created_at=now,
            updated_at=now,
            times_used=0
        )

        # 写入SKILL.md
        skill_md = self._render_skill_md(skill)
        with open(skill_dir / "SKILL.md", 'w', encoding='utf-8') as f:
            f.write(skill_md)

        # 写入metadata.json
        with open(skill_dir / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump(skill.to_dict(), f, ensure_ascii=False, indent=2)

        return str(skill_dir)

    def _render_skill_md(self, skill: Skill) -> str:
        """渲染SKILL.md内容"""
        md = f"""# {skill.name}

## 描述
{skill.description}

## 分类
`{skill.category}`

## 触发关键词
{', '.join(f'`{kw}`' for kw in skill.trigger_keywords)}

## 执行步骤
"""
        for i, step in enumerate(skill.steps, 1):
            md += f"{i}. {step}\n"

        if skill.tools_used:
            md += f"""
## 使用的工具
{', '.join(f'`{t}`' for t in skill.tools_used)}
"""

        if skill.pitfalls:
            md += """
## 注意事项
"""
            for pitfall in skill.pitfalls:
                md += f"- {pitfall}\n"

        if skill.verification:
            md += f"""
## 验证方法
{skill.verification}
"""

        if skill.examples:
            md += """
## 使用示例
"""
            for ex in skill.examples:
                md += f"- {ex}\n"

        md += f"""
---
创建时间: {skill.created_at}
"""
        return md

    def _extract_keywords(self, description: str) -> List:
        """从描述中提取关键词"""
        # 简单的关键词提取：英文单词 + 中文词组
        keywords = []

        # 提取英文单词（3字符以上）
        english_words = re.findall(r'\b[a-zA-Z]{3,}\b', description)
        keywords.extend(english_words[:5])

        # 提取中文关键词（2字符以上）
        chinese = re.findall(r'[\u4e00-\u9fff]{2,}', description)
        keywords.extend(chinese[:5])

        return list(set(keywords))[:10]  # 去重，最多10个

    def search(self, query: str, category: str = None) -> List:
        """
        搜索技能

        Args:
            query: 搜索关键词
            category: 可选，限定分类
        """
        results = []
        query_lower = query.lower()

        search_dirs = [self.skills_dir / category] if category else [
            self.skills_dir / cat for cat in self.SKILL_CATEGORIES
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            for skill_dir in search_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                metadata_file = skill_dir / "metadata.json"
                if not metadata_file.exists():
                    continue

                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)

                    # 检查是否匹配
                    text = (
                        metadata.get("name", "") + " " +
                        metadata.get("description", "") + " " +
                        " ".join(metadata.get("trigger_keywords", []))
                    ).lower()

                    if query_lower in text:
                        metadata["skill_path"] = str(skill_dir)
                        results.append(metadata)

                except Exception:
                    continue

        return results

    def load(self, name: str, category: str = None) -> Optional[Skill]:
        """加载指定技能"""
        sanitized = self._sanitize_name(name)

        if category:
            paths = [self.skills_dir / category / sanitized]
        else:
            paths = [
                self.skills_dir / cat / sanitized
                for cat in self.SKILL_CATEGORIES
            ]

        for path in paths:
            if path.exists():
                metadata_file = path / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    return Skill(**data)

        return None

    def list_all(self, category: str = None) -> List:
        """列出所有技能"""
        results = []

        search_dirs = [self.skills_dir / category] if category else [
            self.skills_dir / cat for cat in self.SKILL_CATEGORIES
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            for skill_dir in search_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                metadata_file = skill_dir / "metadata.json"
                if not metadata_file.exists():
                    continue

                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    metadata["skill_path"] = str(skill_dir)
                    results.append(metadata)
                except Exception:
                    continue

        return sorted(results, key=lambda x: x.get("times_used", 0), reverse=True)

    def increment_usage(self, name: str, category: str = None) -> None:
        """增加技能使用次数"""
        skill = self.load(name, category)
        if skill:
            skill.times_used += 1
            skill.updated_at = datetime.now().isoformat()

            # 更新metadata.json
            path = Path(skill_dir) if 'skill_dir' in dir() else None
            # 重新查找路径
            for cat in self.SKILL_CATEGORIES:
                p = self.skills_dir / cat / self._sanitize_name(name)
                if p.exists():
                    with open(p / "metadata.json", 'w', encoding='utf-8') as f:
                        json.dump(skill.to_dict(), f, ensure_ascii=False, indent=2)
                    break

    def auto_summarize(
        self,
        task_id: str,
        original_description: str,
        subtask_results: list,
        tools_used: list,
        execution_time: float,
        task_file: str = None,
        result_file: str = None
    ) -> str:
        """
        从任务执行经验中自动总结技能

        Args:
            task_id: 任务ID
            original_description: 原始任务描述
            subtask_results: 子任务结果列表
            tools_used: 使用的工具列表
            execution_time: 执行耗时（秒）
            task_file: 任务定义文件路径
            result_file: 结果文件路径

        Returns: 创建的技能路径
        """
        # 提取成功的步骤
        successful_steps = []
        for r in subtask_results:
            if r.get("status") == "completed" and r.get("output"):
                output = r.get("output", "").strip()
                if output:
                    # 简化输出描述
                    if len(output) > 100:
                        output = output[:100] + "..."
                    successful_steps.append(f"执行: {output}")

        if not successful_steps:
            return None

        # 提取工具
        tools = list(set(tools_used))

        # 生成技能名
        # 从描述中提取核心动作
        action_keywords = ["读取", "查看", "统计", "搜索", "创建", "修改", "删除", "执行", "分解", "验证"]
        action = None
        for kw in action_keywords:
            if kw in original_description:
                action = kw
                break

        # 提取目标
        target = ""
        for t in ["config", "scripts", "tasks", "skills", "logs"]:
            if t in original_description:
                target = t
                break

        skill_name = f"{action}_{target}" if action and target else f"task_{task_id[-8:]}"

        # 推断注意事项
        pitfalls = []
        if execution_time > 60:
            pitfalls.append(f"执行耗时较长({execution_time:.0f}秒)，注意超时设置")

        # 检查是否有失败
        has_failure = any(r.get("status") == "failed" for r in subtask_results)
        if has_failure:
            pitfalls.append("注意处理可能的失败情况")

        # 验证方法
        verification = f"检查任务结果文件: {result_file}" if result_file else "验证输出是否符合预期"

        # 使用示例
        examples = [f"用户说: {original_description[:50]}..."]

        # 创建技能
        skill_path = self.create_skill(
            name=skill_name,
            description=f"自动从任务总结: {original_description[:100]}",
            steps=successful_steps,
            tools_used=tools,
            pitfalls=pitfalls if pitfalls else None,
            verification=verification,
            examples=examples,
            category=None,  # 自动推断
            trigger_keywords=[action, target] if action and target else None
        )

        return skill_path


def main():
    """命令行入口"""
    import sys

    manager = SkillManager()

    if len(sys.argv) < 2:
        print("用法:")
        print("  python skill_manager.py list [category]  # 列出技能")
        print("  python skill_manager.py search <关键词> [category]  # 搜索技能")
        print("  python skill_manager.py load <技能名> [category]  # 加载技能")
        print("  python skill_manager.py create <name> <description>  # 创建技能")
        return

    command = sys.argv[1]

    if command == "list":
        category = sys.argv[2] if len(sys.argv) > 2 else None
        skills = manager.list_all(category)
        print(f"技能列表 ({len(skills)}个):")
        for s in skills:
            print(f"  [{s['category']}] {s['name']} - {s['description'][:40]}... (使用{s.get('times_used', 0)}次)")

    elif command == "search":
        if len(sys.argv) < 3:
            print("请提供搜索关键词")
            return
        query = sys.argv[2]
        category = sys.argv[3] if len(sys.argv) > 3 else None
        results = manager.search(query, category)
        print(f"搜索结果 ({len(results)}个):")
        for r in results:
            print(f"  [{r['category']}] {r['name']} - {r['description'][:40]}...")

    elif command == "load":
        if len(sys.argv) < 3:
            print("请提供技能名")
            return
        name = sys.argv[2]
        category = sys.argv[3] if len(sys.argv) > 3 else None
        skill = manager.load(name, category)
        if skill:
            print(f"技能: {skill.name}")
            print(f"描述: {skill.description}")
            print(f"分类: {skill.category}")
            print(f"步骤:")
            for i, step in enumerate(skill.steps, 1):
                print(f"  {i}. {step}")
        else:
            print(f"未找到技能: {name}")

    elif command == "create":
        if len(sys.argv) < 4:
            print("请提供技能名和描述")
            return
        name = sys.argv[2]
        description = sys.argv[3]
        path = manager.create_skill(name, description, steps=["步骤1", "步骤2"])
        print(f"技能已创建: {path}")

    else:
        print(f"未知命令: {command}")


if __name__ == "__main__":
    main()
