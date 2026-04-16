#!/usr/bin/env python3
"""
任务分解器 (Task Decomposer)
将复杂任务分解为原子级别的子任务

原则：
- 原子级别 = 单一工具调用 或 单一子代理任务
- 最大分解深度 = 5
- 每个子任务可独立验证
"""

import json
import re
import yaml
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class SubTask:
    """子任务结构"""
    id: str
    step: int
    description: str
    tool: Optional[str] = None
    skill: Optional[str] = None
    depends_on: list = None
    timeout_seconds: int = 300
    status: str = "pending"
    
    def __post_init__(self):
        if self.depends_on is None:
            self.depends_on = []


@dataclass
class DecomposedTask:
    """分解后的完整任务"""
    task_id: str
    original_description: str
    task_type: str
    priority: str
    subtasks: list
    total_estimated_time: int
    created_at: str
    
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "original_description": self.original_description,
            "task_type": self.task_type,
            "priority": self.priority,
            "subtasks": [asdict(s) for s in self.subtasks],
            "total_estimated_time": self.total_estimated_time,
            "created_at": self.created_at
        }


class TaskDecomposer:
    """任务分解器"""
    
    # 任务类型关键词
    TASK_TYPE_KEYWORDS = {
        "query_search": ["搜索", "查询", "查找", "找", "搜", "search", "find", "query"],
        "file_operation": ["读取", "写入", "编辑", "移动", "删除", "复制", "创建", "read", "write", "edit", "move", "delete", "copy", "create", "file"],
        "browser_operation": ["网页", "浏览器", "点击", "填表", "登录", "web", "browser", "click", "navigate"],
        "complex_task": ["多步骤", "复杂", "委托", "开发", "构建", "分析", "总结", "报告", "complex", "develop", "build", "analyze"]
    }
    
    # 性能基准（秒）
    PERFORMANCE_BASELINE = {
        "query_search": 120,
        "file_operation": 300,
        "browser_operation": 300,
        "complex_task": 1800
    }
    
    # 工具映射
    TOOL_MAPPING = {
        "terminal": ["执行", "命令", "运行", "bash", "shell", "终端", "查看", "列出", "显示", "看", "找", "统计", "搜索", "ls", "cat", "grep", "find", "wc", "git"],
        "read_file": ["读取文件", "查看文件", "cat文件", "打开文件"],
        "write_file": ["写入", "创建文件", "新建文件", "write", "create file"],
        "patch": ["编辑", "修改文件", "替换", "edit file", "modify"],
        "search_files": ["搜索内容", "grep", "search in"],
        "browser_navigate": ["打开", "访问", "导航", "open", "navigate", "go to", "网页"],
        "browser_click": ["点击", "click"],
        "browser_type": ["输入", "填写", "type"],
        "delegate_task": ["委托", "分配", "子代理", "delegate", "subagent"],
    }
    
    def __init__(self, schema_path: str = None):
        self.schema = self._load_schema(schema_path) if schema_path else {}
        self.max_depth = self.schema.get("decomposer", {}).get("max_depth", 5)
    
    def _load_schema(self, path: str) -> dict:
        """加载Schema配置"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    
    def _generate_task_id(self) -> str:
        """生成任务ID"""
        return f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}_{id(self) % 10000}"
    
    def _classify_task_type(self, description: str) -> str:
        """识别任务类型"""
        desc_lower = description.lower()
        scores = {}
        
        for task_type, keywords in self.TASK_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in desc_lower)
            scores[task_type] = score
        
        if max(scores.values()) == 0:
            return "complex_task"
        
        return max(scores, key=scores.get)
    
    def _determine_priority(self, description: str) -> str:
        """判断任务优先级"""
        urgent_keywords = ["紧急", "马上", "立即", "尽快", "急", "urgent", "asap", "important"]
        simple_keywords = ["简单", "一下", "看看", "查一下", "帮我", "easy", "simple", "quick"]
        
        desc_lower = description.lower()
        is_urgent = any(kw in desc_lower for kw in urgent_keywords)
        is_simple = any(kw in desc_lower for kw in simple_keywords)
        
        if is_urgent and is_simple:
            return "P0"
        elif is_urgent:
            return "P1"
        else:
            return "P2"
    
    def _extract_tools(self, description: str) -> list:
        """提取需要的工具（按优先级）"""
        desc_lower = description.lower()
        found_tools = []
        
        # 按优先级顺序检查（terminal放最后因为它最宽泛）
        tool_order = [
            "delegate_task", "browser_navigate", "browser_click", "browser_type",
            "search_files", "patch", "write_file", "read_file", "terminal"
        ]
        
        for tool in tool_order:
            keywords = self.TOOL_MAPPING.get(tool, [])
            if any(kw.lower() in desc_lower for kw in keywords):
                # terminal太宽泛，只在没有其他匹配时用它
                if tool == "terminal" and found_tools:
                    continue
                found_tools.append(tool)
        
        # 如果没有匹配任何工具，默认用terminal
        return found_tools if found_tools else ["terminal"]
    
    def _is_atomic(self, description: str) -> bool:
        """判断是否已经是原子任务"""
        atomic_keywords = ["查看", "读取", "执行", "运行", "打开", "访问", 
                          "查看", "cat", "ls", "cd", "git", "搜索"]
        compound_keywords = ["然后", "之后", "接着", "再", "和", "以及", 
                           "并且", "首先", "其次", "最后", "and then", "after"]
        
        desc_lower = description.lower()
        has_compound = any(kw in desc_lower for kw in compound_keywords)
        
        return not has_compound
    
    def _split_compound_task(self, description: str) -> list:
        """拆分复合任务"""
        # 按连接词拆分
        separators = ["然后", "之后", "接着", "再", "首先", "其次", "最后",
                     "and then", "after", "next", "finally"]
        
        parts = [description]
        for sep in separators:
            new_parts = []
            for part in parts:
                new_parts.extend(part.split(sep))
            parts = new_parts
        
        # 清理每个部分
        result = []
        for i, part in enumerate(parts):
            part = part.strip()
            # 移除句首的连接词
            for sep in ["然后", "之后", "接着", "再", "首先", "其次"]:
                if part.startswith(sep):
                    part = part[len(sep):].strip()
            if part:
                result.append((i + 1, part))
        
        return result
    
    def _estimate_time(self, task_type: str, num_steps: int) -> int:
        """估算任务时间"""
        base_time = self.PERFORMANCE_BASELINE.get(task_type, 300)
        # 每个额外步骤增加50%基础时间
        return int(base_time * (1 + 0.5 * (num_steps - 1)))
    
    def decompose(self, description: str, depth: int = 0) -> DecomposedTask:
        """
        分解任务
        
        Args:
            description: 任务描述
            depth: 当前深度
            
        Returns:
            DecomposedTask: 分解后的任务对象
        """
        task_id = self._generate_task_id()
        task_type = self._classify_task_type(description)
        priority = self._determine_priority(description)
        base_timeout = self.PERFORMANCE_BASELINE.get(task_type, 300)
        
        # 如果已经是原子任务
        if self._is_atomic(description) or depth >= self.max_depth:
            tools = self._extract_tools(description)
            return DecomposedTask(
                task_id=task_id,
                original_description=description,
                task_type=task_type,
                priority=priority,
                subtasks=[SubTask(
                    id=f"{task_id}_1",
                    step=1,
                    description=description,
                    tool=tools[0] if tools else "terminal",
                    timeout_seconds=base_timeout
                )],
                total_estimated_time=base_timeout,
                created_at=datetime.now().isoformat()
            )
        
        # 拆分复合任务
        parts = self._split_compound_task(description)
        
        subtasks = []
        for idx, (step_num, part_desc) in enumerate(parts):
            # 递归分解每个部分
            sub_task = self.decompose(part_desc, depth + 1)
            
            # 如果子任务可以进一步分解
            if len(sub_task.subtasks) > 1:
                for i, st in enumerate(sub_task.subtasks):
                    st.id = f"{task_id}_{idx}_{i + 1}"
                    st.step = idx * 100 + i + 1
                    if i > 0:
                        st.depends_on = [f"{task_id}_{idx}_{i}"]
                subtasks.extend(sub_task.subtasks)
            else:
                sub_task.subtasks[0].id = f"{task_id}_{idx + 1}"
                sub_task.subtasks[0].step = idx + 1
                if idx > 0:
                    sub_task.subtasks[0].depends_on = [f"{task_id}_{idx}"]
                subtasks.append(sub_task.subtasks[0])
        
        # 计算总时间
        total_time = self._estimate_time(task_type, len(subtasks))
        
        return DecomposedTask(
            task_id=task_id,
            original_description=description,
            task_type=task_type,
            priority=priority,
            subtasks=subtasks,
            total_estimated_time=total_time,
            created_at=datetime.now().isoformat()
        )
    
    def save(self, task: DecomposedTask, output_dir: str = None) -> str:
        """保存分解结果到文件"""
        if output_dir is None:
            output_dir = Path.home() / ".hermes" / "repos" / "mochenhermes" / "tasks"
        
        output_path = Path(output_dir) / f"{task.task_id}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(task.to_dict(), f, ensure_ascii=False, indent=2)
        
        return str(output_path)


def main():
    """命令行入口"""
    if len(__import__('sys').argv) < 2:
        print("用法: python task_decomposer.py <任务描述>")
        print("示例: python task_decomposer.py 帮我读取config目录下的所有yaml文件")
        return
    
    description = " ".join(__import__('sys').argv[1:])
    
    decomposer = TaskDecomposer()
    result = decomposer.decompose(description)
    
    # 输出结果
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    
    # 保存到文件
    output_path = decomposer.save(result)
    print(f"\n任务已保存到: {output_path}")


if __name__ == "__main__":
    main()
