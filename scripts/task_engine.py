#!/usr/bin/env python3
"""
任务执行引擎 (Task Execution Engine)
驱动任务自动执行的核心引擎

职责：
1. 按依赖顺序调度子任务
2. 调用对应工具执行
3. 处理失败重试
4. 记录执行状态和时间
5. 完成后触发验证
"""

import json
import time
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class SubTaskResult:
    """子任务执行结果"""
    subtask_id: str
    step: int
    status: str  # pending/running/completed/failed
    tool: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    output: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0


@dataclass
class ExecutionResult:
    """任务执行结果"""
    task_id: str
    status: str  # pending/running/completed/failed
    subtask_results: list
    total_time_seconds: float
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0


class ToolExecutor:
    """工具执行器 — 将工具名映射到实际执行函数"""
    
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = Path.home() / ".hermes" / "repos" / "mochenhermes"
        self.base_dir = Path(base_dir)
        
        # 工具注册表
        self.tools = {
            "terminal": self._exec_terminal,
            "read_file": self._exec_read_file,
            "write_file": self._exec_write_file,
            "patch": self._exec_patch,
            "search_files": self._exec_search_files,
            "browser_navigate": self._exec_browser_navigate,
            "browser_click": self._exec_browser_click,
            "browser_type": self._exec_browser_type,
            "delegate_task": self._exec_delegate,
        }
    
    def execute(self, tool: str, params: dict) -> dict:
        """执行工具"""
        if tool not in self.tools:
            return {
                "success": False,
                "error": f"未知工具: {tool}",
                "output": None
            }
        
        try:
            return self.tools[tool](params)
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _exec_terminal(self, params: dict) -> dict:
        """执行终端命令"""
        command = params.get("command", "")
        workdir = params.get("workdir", str(self.base_dir))
        timeout = params.get("timeout", 300)
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"命令超时 ({timeout}秒)",
                "output": None,
                "exit_code": -1
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None,
                "exit_code": -1
            }
    
    def _exec_read_file(self, params: dict) -> dict:
        """读取文件"""
        file_path = params.get("path", "")
        offset = params.get("offset", 1)
        limit = params.get("limit", 500)
        
        try:
            full_path = Path(file_path)
            if not full_path.is_absolute():
                full_path = self.base_dir / full_path
            
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            content = ''.join(lines[offset-1:offset-1+limit])
            
            return {
                "success": True,
                "output": content,
                "total_lines": total_lines,
                "path": str(full_path)
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": f"文件不存在: {file_path}",
                "output": None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _exec_write_file(self, params: dict) -> dict:
        """写入文件"""
        file_path = params.get("path", "")
        content = params.get("content", "")
        
        try:
            full_path = Path(file_path)
            if not full_path.is_absolute():
                full_path = self.base_dir / full_path
            
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "output": f"文件已写入: {full_path}",
                "path": str(full_path)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _exec_patch(self, params: dict) -> dict:
        """编辑文件（简单版本，实际应用中会用更复杂的逻辑）"""
        file_path = params.get("path", "")
        old_string = params.get("old_string", "")
        new_string = params.get("new_string", "")
        
        try:
            full_path = Path(file_path)
            if not full_path.is_absolute():
                full_path = self.base_dir / full_path
            
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_string not in content:
                return {
                    "success": False,
                    "error": f"未找到要替换的文本: {old_string[:50]}...",
                    "output": None
                }
            
            new_content = content.replace(old_string, new_string)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return {
                "success": True,
                "output": f"文件已修改: {full_path}",
                "path": str(full_path)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _exec_search_files(self, params: dict) -> dict:
        """搜索文件内容"""
        pattern = params.get("pattern", "")
        path = params.get("path", str(self.base_dir))
        
        try:
            result = subprocess.run(
                f"grep -rn '{pattern}' {path}",
                shell=True,
                capture_output=True,
                text=True
            )
            return {
                "success": result.returncode in [0, 1],  # 0找到, 1没找到都算正常
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }
    
    def _exec_browser_navigate(self, params: dict) -> dict:
        """浏览器导航（占位，实际需要浏览器工具）"""
        return {
            "success": False,
            "error": "浏览器工具暂未集成，请手动执行或使用browser工具",
            "output": None
        }
    
    def _exec_browser_click(self, params: dict) -> dict:
        """浏览器点击（占位）"""
        return {
            "success": False,
            "error": "浏览器工具暂未集成",
            "output": None
        }
    
    def _exec_browser_type(self, params: dict) -> dict:
        """浏览器输入（占位）"""
        return {
            "success": False,
            "error": "浏览器工具暂未集成",
            "output": None
        }
    
    def _exec_delegate(self, params: dict) -> dict:
        """委托子代理（占位，实际需要子代理系统）"""
        return {
            "success": False,
            "error": "子代理委托暂未集成",
            "output": None
        }


class TaskExecutionEngine:
    """任务执行引擎"""
    
    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 4, 8]  # 指数退避
    
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = Path.home() / ".hermes" / "repos" / "mochenhermes"
        
        self.base_dir = Path(base_dir)
        self.tasks_dir = self.base_dir / "tasks"
        self.logs_dir = self.base_dir / "logs"
        
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self.tool_executor = ToolExecutor(base_dir)
    
    def _load_task(self, task_id: str) -> dict:
        """加载任务定义"""
        task_path = self.tasks_dir / f"{task_id}.json"
        
        if not task_path.exists():
            raise FileNotFoundError(f"任务文件不存在: {task_id}")
        
        with open(task_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _save_result(self, result: ExecutionResult) -> tuple:
        """保存执行结果，返回(path, data)"""
        result_path = self.tasks_dir / f"{result.task_id}_result.json"
        
        result_data = {
            "task_id": result.task_id,
            "status": result.status,
            "subtask_results": [asdict(r) for r in result.subtask_results],
            "total_time_seconds": result.total_time_seconds,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "error": result.error,
            "retry_count": result.retry_count
        }
        
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        return str(result_path), result_data
    
    def _log(self, level: str, task_id: str, message: str) -> None:
        """记录日志"""
        log_file = self.logs_dir / f"engine_{datetime.now().strftime('%Y%m%d')}.log"
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{level}] [{task_id}] {message}\n"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    
    def _wait_before_retry(self, retry_count: int) -> None:
        """等待后重试"""
        delay = self.RETRY_DELAYS[min(retry_count, len(self.RETRY_DELAYS) - 1)]
        time.sleep(delay)
    
    def _build_command_from_description(self, description: str) -> str:
        """从描述中提取实际命令（智能解析）"""
        # 清理描述末尾的标点和空白
        desc = description.strip().rstrip('，,').rstrip('。.')
        
        # 如果描述已经是英文命令，直接返回
        if any(cmd in desc for cmd in ["ls", "cat", "grep", "find", "wc", "echo", "cd", "git", "python"]):
            return desc
        
        # 中文描述转换
        commands = []
        
        # 目录+文件列表类命令
        if any(kw in desc for kw in ["查看", "列出", "显示", "看"]):
            # 已知目录
            known_dirs = ["scripts", "config", "tasks", "logs", "skills", "memory"]
            dir_path = None
            
            for d in known_dirs:
                if d in desc:
                    dir_path = d
                    break
            
            if dir_path:
                if not dir_path.startswith("/"):
                    dir_path = f"{self.base_dir}/{dir_path}"
                
                # 是否过滤文件类型
                if "py" in desc:
                    commands.append(f"ls {dir_path}/*.py 2>/dev/null || ls {dir_path}/")
                elif "yaml" in desc:
                    commands.append(f"ls {dir_path}/*.yaml 2>/dev/null || ls {dir_path}/")
                else:
                    commands.append(f"ls {dir_path}/")
                return " && ".join(commands)
        
        if "读取" in desc or "查看" in desc:
            if "config" in desc:
                if "yaml" in desc or "所有" in desc:
                    commands.append(f"ls {self.base_dir}/config/")
                    commands.append(f"wc -l {self.base_dir}/config/*.yaml")
            elif "目录" in desc:
                path = desc.split("目录")[0].split("读取")[1] if "读取" in desc else desc.split("目录")[0]
                path = path.replace("下", "").strip()
                if not path.startswith("/"):
                    path = f"{self.base_dir}/{path}"
                commands.append(f"ls {path}")
        
        if "统计" in desc or "行数" in desc:
            if "yaml" in desc:
                commands.append(f"wc -l {self.base_dir}/config/*.yaml")
            else:
                # 尝试从描述中提取目录
                import re
                dir_match = re.search(r'([^\s]+)目录', desc)
                if dir_match:
                    dir_path = dir_match.group(1)
                    if not dir_path.startswith("/"):
                        dir_path = f"{self.base_dir}/{dir_path}"
                    commands.append(f"wc -l {dir_path}/*")
        
        if "搜索" in desc or "查找" in desc:
            # 提取搜索模式
            pattern = desc.split("搜索")[1].split("文件")[0].strip() if "搜索" in desc else ""
            commands.append(f"grep -rn '{pattern}' {self.base_dir}")
        
        return " && ".join(commands) if commands else desc
    
    def _execute_subtask(self, subtask: dict, task_id: str) -> SubTaskResult:
        """执行单个子任务"""
        subtask_id = subtask["id"]
        tool = subtask.get("tool", "terminal")
        description = subtask.get("description", "")
        timeout = subtask.get("timeout_seconds", 300)
        
        self._log("INFO", task_id, f"开始执行子任务: {subtask_id} (tool={tool})")
        
        # 构建执行参数
        params = {
            "description": description,
            "timeout": timeout
        }
        
        # 根据工具添加特定参数
        if tool == "terminal":
            # 智能解析描述中的命令
            params["command"] = self._build_command_from_description(description)
            params["workdir"] = str(self.base_dir)
        elif tool == "read_file":
            # 从描述中提取文件路径
            if "config" in description:
                params["path"] = f"{self.base_dir}/config/task_schema.yaml"
            else:
                params["path"] = description.replace("读取", "").replace("查看", "").replace("文件", "").strip()
        elif tool == "write_file":
            params["path"] = subtask.get("file_path", "")
            params["content"] = subtask.get("file_content", "")
        
        # 执行
        start_time = datetime.now()
        result = self.tool_executor.execute(tool, params)
        end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        
        subtask_result = SubTaskResult(
            subtask_id=subtask_id,
            step=subtask.get("step", 0),
            status="completed" if result["success"] else "failed",
            tool=tool,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration_seconds=duration,
            output=result.get("output"),
            error=result.get("error"),
            retry_count=0
        )
        
        if result["success"]:
            self._log("INFO", task_id, f"子任务完成: {subtask_id} ({duration:.2f}秒)")
        else:
            self._log("ERROR", task_id, f"子任务失败: {subtask_id} - {result.get('error')}")
        
        return subtask_result
    
    def _can_execute(self, subtask: dict, completed_ids: set) -> bool:
        """检查子任务是否可以执行（依赖已满足）"""
        depends_on = subtask.get("depends_on", [])
        
        if not depends_on:
            return True
        
        return all(dep_id in completed_ids for dep_id in depends_on)
    
    def execute(self, task_id: str, max_workers: int = 3) -> ExecutionResult:
        """
        执行任务
        
        Args:
            task_id: 任务ID
            max_workers: 最大并行数
        """
        self._log("INFO", task_id, f"任务开始执行 (max_workers={max_workers})")
        
        # 加载任务
        task = self._load_task(task_id)
        subtasks = task.get("subtasks", [])
        
        # 初始化结果
        started_at = datetime.now().isoformat()
        subtask_results = []
        completed_ids = set()
        failed_ids = set()
        
        # 创建结果字典
        result_map = {}
        
        # 按step排序
        sorted_subtasks = sorted(subtasks, key=lambda x: x.get("step", 0))
        
        # 简单串行执行（保持依赖顺序）
        for subtask in sorted_subtasks:
            subtask_id = subtask["id"]
            
            # 检查依赖
            if not self._can_execute(subtask, completed_ids):
                # 等待依赖完成
                self._log("WARN", task_id, f"子任务 {subtask_id} 等待依赖: {subtask.get('depends_on')}")
                # 这里简化处理，实际需要更好的等待机制
            
            # 重试逻辑
            for retry_count in range(self.MAX_RETRIES):
                result = self._execute_subtask(subtask, task_id)
                
                if result.status == "completed":
                    result_map[subtask_id] = result
                    completed_ids.add(subtask_id)
                    subtask_results.append(result)
                    break
                else:
                    if retry_count < self.MAX_RETRIES - 1:
                        self._log("WARN", task_id, f"子任务 {subtask_id} 重试 ({retry_count + 1}/{self.MAX_RETRIES})")
                        self._wait_before_retry(retry_count)
                        result.retry_count = retry_count + 1
                    else:
                        result_map[subtask_id] = result
                        completed_ids.add(subtask_id)
                        failed_ids.add(subtask_id)
                        subtask_results.append(result)
                        self._log("ERROR", task_id, f"子任务 {subtask_id} 失败 (已达最大重试次数)")
        
        # 计算总时间
        completed_at = datetime.now()
        start_dt = datetime.fromisoformat(started_at)
        total_time = (completed_at - start_dt).total_seconds()
        
        # 判断最终状态
        final_status = "completed" if len(failed_ids) == 0 else "failed"
        error = None
        if failed_ids:
            error = f"失败子任务: {', '.join(failed_ids)}"
        
        # 构建结果
        execution_result = ExecutionResult(
            task_id=task_id,
            status=final_status,
            subtask_results=subtask_results,
            total_time_seconds=total_time,
            started_at=started_at,
            completed_at=completed_at.isoformat(),
            error=error,
            retry_count=max(r.retry_count for r in subtask_results) if subtask_results else 0
        )
        
        # 保存结果
        result_path, result_data = self._save_result(execution_result)
        
        # 保存顶层result字段（供验证器使用）
        if completed_ids and len(failed_ids) == 0:
            # 所有子任务成功，生成汇总result
            outputs = [r.output for r in subtask_results if r.output]
            summary = "\n".join(outputs) if outputs else "任务完成"
            
            result_data["result"] = summary
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        self._log("INFO", task_id, f"任务执行完成: status={final_status}, time={total_time:.2f}秒")
        
        return execution_result


def main():
    """命令行入口"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python task_engine.py <任务ID> [max_workers]")
        print("示例: python task_engine.py task_20260416185757_2848")
        return
    
    task_id = sys.argv[1]
    max_workers = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    engine = TaskExecutionEngine()
    
    try:
        result = engine.execute(task_id, max_workers)
        
        print(f"执行完成!")
        print(f"任务ID: {result.task_id}")
        print(f"状态: {result.status}")
        print(f"总耗时: {result.total_time_seconds:.2f}秒")
        print(f"子任务数: {len(result.subtask_results)}")
        
        for r in result.subtask_results:
            status_icon = "✓" if r.status == "completed" else "✗"
            print(f"  {status_icon} {r.subtask_id}: {r.status} ({r.duration_seconds:.2f}秒)")
            if r.error:
                print(f"    错误: {r.error[:100]}")
        
        if result.error:
            print(f"\n错误: {result.error}")
        
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"执行出错: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
