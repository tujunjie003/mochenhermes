#!/usr/bin/env python3
"""
任务监控器 (Task Monitor)
监控任务执行状态，失败时发送告警

功能：
1. 定期检查待执行任务
2. 跟踪执行中的任务状态
3. 失败任务重试 + 通知
4. 执行日志记录
"""

import json
import time
import yaml
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskRecord:
    """任务执行记录"""
    task_id: str
    description: str
    task_type: str
    priority: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0
    error: Optional[str] = None
    total_time_seconds: Optional[float] = None
    
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "description": self.description,
            "task_type": self.task_type,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
            "error": self.error,
            "total_time_seconds": self.total_time_seconds
        }


class TaskMonitor:
    """任务监控器"""
    
    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 4, 8]  # 指数退避：2s, 4s, 8s
    
    # 性能基准（秒）
    PERFORMANCE_BASELINE = {
        "query_search": 120,
        "file_operation": 300,
        "browser_operation": 300,
        "complex_task": 1800
    }
    
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = Path.home() / ".hermes" / "repos" / "mochenhermes"
        
        self.base_dir = Path(base_dir)
        self.tasks_dir = self.base_dir / "tasks"
        self.logs_dir = self.base_dir / "logs"
        self.config_dir = self.base_dir / "config"
        
        # 确保目录存在
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载配置
        self.schema = self._load_schema()
    
    def _load_schema(self) -> dict:
        """加载Schema配置"""
        schema_path = self.config_dir / "task_schema.yaml"
        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    
    def _get_retry_config(self) -> dict:
        """获取重试配置"""
        retry_config = self.schema.get("retry", {})
        return {
            "max_attempts": retry_config.get("max_attempts", self.MAX_RETRIES),
            "delays": retry_config.get("backoff_delays", self.RETRY_DELAYS)
        }
    
    def _load_task(self, task_id: str) -> dict:
        """加载任务定义"""
        task_path = self.tasks_dir / f"{task_id}.json"
        if not task_path.exists():
            raise FileNotFoundError(f"任务不存在: {task_id}")
        
        with open(task_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _save_result(self, task_id: str, result: dict) -> str:
        """保存执行结果"""
        result_path = self.tasks_dir / f"{task_id}_result.json"
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return str(result_path)
    
    def _load_result(self, task_id: str) -> dict:
        """加载执行结果"""
        result_path = self.tasks_dir / f"{task_id}_result.json"
        if not result_path.exists():
            raise FileNotFoundError(f"结果不存在: {task_id}")
        
        with open(result_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _update_task_status(self, task_id: str, status: str, error: str = None) -> None:
        """更新任务文件中的状态"""
        task = self._load_task(task_id)
        
        # 更新任务状态
        for st in task.get("subtasks", []):
            if st.get("status") == "running":
                st["status"] = status
                if error:
                    st["error"] = error
        
        # 保存更新后的任务
        task_path = self.tasks_dir / f"{task_id}.json"
        with open(task_path, 'w', encoding='utf-8') as f:
            json.dump(task, f, ensure_ascii=False, indent=2)
    
    def _log(self, level: str, task_id: str, message: str) -> None:
        """记录日志"""
        log_file = self.logs_dir / f"monitor_{datetime.now().strftime('%Y%m%d')}.log"
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{level}] [{task_id}] {message}\n"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    
    def _check_timeout(self, task_id: str) -> tuple[bool, str]:
        """检查任务是否超时"""
        try:
            task = self._load_task(task_id)
            result = self._load_result(task_id)
        except FileNotFoundError:
            return False, ""
        
        estimated_time = task.get("total_estimated_time", 300)
        actual_time = result.get("total_time_seconds", 0)
        
        if actual_time > estimated_time:
            return True, f"任务超时: 实际{actual_time}秒 > 预估{estimated_time}秒"
        return False, ""
    
    def _should_retry(self, task_id: str) -> tuple[bool, int]:
        """判断是否应该重试，返回(应该重试, 当前重试次数)"""
        try:
            result = self._load_result(task_id)
        except FileNotFoundError:
            return True, 0
        
        retry_count = result.get("retry_count", 0)
        max_retries = self._get_retry_config()["max_attempts"]
        
        if retry_count >= max_retries:
            return False, retry_count
        
        return True, retry_count
    
    def _wait_before_retry(self, retry_count: int) -> None:
        """等待后重试"""
        delays = self._get_retry_config()["delays"]
        delay = delays[min(retry_count, len(delays) - 1)]
        time.sleep(delay)
    
    def record_start(self, task_id: str) -> None:
        """记录任务开始"""
        self._log("INFO", task_id, "任务开始执行")
        self._update_task_status(task_id, "running")
    
    def record_complete(self, task_id: str, result: dict) -> None:
        """记录任务完成"""
        result["status"] = "completed"
        result["completed_at"] = datetime.now().isoformat()
        
        self._save_result(task_id, result)
        self._log("INFO", task_id, f"任务完成，耗时{result.get('total_time_seconds', 0)}秒")
    
    def record_failure(self, task_id: str, error: str, result: dict = None) -> None:
        """记录任务失败"""
        # 检查是否超时
        is_timeout, timeout_msg = self._check_timeout(task_id)
        if is_timeout:
            error = f"{error}; {timeout_msg}"
        
        # 检查是否应该重试
        should_retry, retry_count = self._should_retry(task_id)
        
        if result is None:
            result = {}
        
        result["status"] = "failed"
        result["error"] = error
        result["retry_count"] = retry_count
        result["failed_at"] = datetime.now().isoformat()
        
        self._save_result(task_id, result)
        
        if should_retry:
            self._log("WARN", task_id, f"任务失败 (重试 {retry_count + 1}/{self._get_retry_config()['max_attempts']}): {error}")
            self._wait_before_retry(retry_count)
            # 重试时会重新调用 record_start
        else:
            self._log("ERROR", task_id, f"任务失败 (已达最大重试次数): {error}")
            # 发送告警通知
            self._send_alert(task_id, error)
    
    def _send_alert(self, task_id: str, error: str) -> None:
        """发送告警通知（飞书）"""
        # TODO: 实现飞书告警
        # 目前只记录日志
        self._log("ALERT", task_id, f"发送告警: {error}")
    
    def get_pending_tasks(self) -> list:
        """获取待执行任务"""
        pending = []
        
        for task_file in self.tasks_dir.glob("task_*.json"):
            if "_result" in task_file.name or "_verification" in task_file.name:
                continue
            
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    task = json.load(f)
                
                # 检查是否已有结果
                result_file = self.tasks_dir / f"{task['task_id']}_result.json"
                if result_file.exists():
                    continue
                
                pending.append(task)
            except Exception:
                continue
        
        return pending
    
    def get_running_tasks(self) -> list:
        """获取执行中的任务"""
        running = []
        
        for task_file in self.tasks_dir.glob("task_*.json"):
            if "_result" in task_file.name or "_verification" in task_file.name:
                continue
            
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    task = json.load(f)
                
                # 检查是否有running状态的子任务
                has_running = any(
                    st.get("status") == "running" 
                    for st in task.get("subtasks", [])
                )
                
                if has_running:
                    running.append(task)
            except Exception:
                continue
        
        return running
    
    def get_failed_tasks(self) -> list:
        """获取失败任务"""
        failed = []
        
        for result_file in self.tasks_dir.glob("task_*_result.json"):
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                
                if result.get("status") == "failed":
                    task_id = result_file.name.replace("_result.json", "")
                    task = self._load_task(task_id)
                    failed.append({
                        "task": task,
                        "result": result
                    })
            except Exception:
                continue
        
        return failed
    
    def get_statistics(self) -> dict:
        """获取任务统计信息"""
        stats = {
            "total": 0,
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "by_type": {},
            "by_priority": {}
        }
        
        for task_file in self.tasks_dir.glob("task_*.json"):
            if "_result" in task_file.name or "_verification" in task_file.name:
                continue
            
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    task = json.load(f)
                
                stats["total"] += 1
                
                task_type = task.get("task_type", "unknown")
                priority = task.get("priority", "P2")
                
                stats["by_type"][task_type] = stats["by_type"].get(task_type, 0) + 1
                stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1
                
                # 检查状态
                result_file = self.tasks_dir / f"{task['task_id']}_result.json"
                if result_file.exists():
                    with open(result_file, 'r', encoding='utf-8') as f:
                        result = json.load(f)
                    status = result.get("status", "unknown")
                    if status == "completed":
                        stats["completed"] += 1
                    elif status == "failed":
                        stats["failed"] += 1
                else:
                    stats["pending"] += 1
                    
            except Exception:
                continue
        
        return stats
    
    def run_monitoring_cycle(self) -> dict:
        """运行一次监控周期"""
        stats = self.get_statistics()
        pending = self.get_pending_tasks()
        running = self.get_running_tasks()
        failed = self.get_failed_tasks()
        
        monitoring_result = {
            "timestamp": datetime.now().isoformat(),
            "statistics": stats,
            "pending_tasks": [t["task_id"] for t in pending],
            "running_tasks": [t["task_id"] for t in running],
            "failed_tasks": [
                {
                    "task_id": f["task"]["task_id"],
                    "error": f["result"].get("error", "未知错误"),
                    "retry_count": f["result"].get("retry_count", 0)
                }
                for f in failed
            ],
            "actions_taken": []
        }
        
        # 处理失败任务
        for f in failed:
            task_id = f["task"]["task_id"]
            should_retry, retry_count = self._should_retry(task_id)
            
            if should_retry:
                monitoring_result["actions_taken"].append({
                    "action": "retry",
                    "task_id": task_id,
                    "retry_count": retry_count + 1
                })
        
        # 记录监控周期
        self._log("INFO", "MONITOR", f"监控周期: {stats['total']}个任务, {stats['pending']}待执行, {stats['running']}执行中, {stats['completed']}完成, {stats['failed']}失败")
        
        return monitoring_result


def main():
    """命令行入口"""
    import sys
    
    monitor = TaskMonitor()
    
    if len(sys.argv) < 2:
        # 无参数：运行一次监控
        result = monitor.run_monitoring_cycle()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    
    command = sys.argv[1]
    
    if command == "stats":
        # 显示统计
        stats = monitor.get_statistics()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    
    elif command == "pending":
        # 显示待执行任务
        pending = monitor.get_pending_tasks()
        print(f"待执行任务 ({len(pending)}个):")
        for t in pending:
            print(f"  - {t['task_id']}: {t['original_description'][:50]}...")
    
    elif command == "failed":
        # 显示失败任务
        failed = monitor.get_failed_tasks()
        print(f"失败任务 ({len(failed)}个):")
        for f in failed:
            print(f"  - {f['task']['task_id']}: {f['result'].get('error', '未知')[:50]}...")
    
    elif command == "monitor":
        # 运行一次监控
        result = monitor.run_monitoring_cycle()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    else:
        print(f"未知命令: {command}")
        print("可用命令: stats, pending, failed, monitor")
        sys.exit(1)


if __name__ == "__main__":
    main()
