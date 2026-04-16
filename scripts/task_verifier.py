#!/usr/bin/env python3
"""
任务验证器 (Task Verifier)
在任务完成后、交付前进行自检

验证维度：
1. 完整性 — 所有步骤都执行了
2. 正确性 — 输出格式/内容符合预期
3. 时效性 — 没有超时
4. 幂等性 — 重复执行结果一致（可选）
"""

import json
import yaml
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Callable
from pathlib import Path


@dataclass
class VerificationResult:
    """验证结果"""
    task_id: str
    passed: bool
    checks: dict
    errors: list
    warnings: list
    verified_at: str
    
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "passed": self.passed,
            "checks": self.checks,
            "errors": self.errors,
            "warnings": self.warnings,
            "verified_at": self.verified_at
        }


class TaskVerifier:
    """任务验证器"""
    
    # 默认检查项
    DEFAULT_CHECKS = {
        "completeness": True,   # 所有步骤完成
        "format": True,          # 输出格式正确
        "timeout": True,          # 未超时
        "error_free": True,      # 无错误
    }
    
    def __init__(self, schema_path: str = None):
        self.schema = self._load_schema(schema_path) if schema_path else {}
        self.default_checks = self.schema.get("verification", {}).get("checks", self.DEFAULT_CHECKS)
    
    def _load_schema(self, path: str) -> dict:
        """加载Schema配置"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    
    def _load_task(self, task_id: str, tasks_dir: str = None) -> dict:
        """加载任务定义"""
        if tasks_dir is None:
            tasks_dir = Path.home() / ".hermes" / "repos" / "mochenhermes" / "tasks"
        
        task_path = Path(tasks_dir) / f"{task_id}.json"
        
        if not task_path.exists():
            raise FileNotFoundError(f"任务文件不存在: {task_path}")
        
        with open(task_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_result(self, task_id: str, results_dir: str = None) -> dict:
        """加载任务执行结果"""
        if results_dir is None:
            results_dir = Path.home() / ".hermes" / "repos" / "mochenhermes" / "tasks"
        
        result_path = Path(results_dir) / f"{task_id}_result.json"
        
        if not result_path.exists():
            raise FileNotFoundError(f"结果文件不存在: {result_path}")
        
        with open(result_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def verify_completeness(self, task: dict, result: dict) -> tuple[bool, str]:
        """验证完整性：所有子任务都已完成"""
        subtasks = task.get("subtasks", [])
        completed_ids = set()
        
        # 从结果中提取完成的子任务
        if "subtask_results" in result:
            for sr in result["subtask_results"]:
                if sr.get("status") == "completed":
                    completed_ids.add(sr.get("subtask_id"))
        
        # 检查每个子任务
        missing = []
        for st in subtasks:
            if st["id"] not in completed_ids and st.get("status") != "skipped":
                missing.append(st["id"])
        
        if missing:
            return False, f"以下子任务未完成: {', '.join(missing)}"
        return True, "所有子任务已完成"
    
    def verify_format(self, result: dict, expected_format: str = None) -> tuple[bool, str]:
        """验证格式：输出格式是否符合预期"""
        if expected_format is None:
            # 默认检查result字段存在
            if "result" not in result and "output" not in result:
                return False, "结果中缺少 result 或 output 字段"
            return True, "格式正确"
        
        # 按预期格式验证
        if expected_format == "json":
            try:
                if "result" in result:
                    json.loads(result["result"])
                return True, "JSON格式正确"
            except json.JSONDecodeError:
                return False, "result字段不是有效的JSON"
        
        elif expected_format == "file":
            if "output_file" not in result:
                return False, "缺少output_file字段"
            output_path = Path(result["output_file"])
            if not output_path.exists():
                return False, f"输出文件不存在: {output_path}"
            return True, f"输出文件存在: {output_path}"
        
        return True, "格式验证通过"
    
    def verify_timeout(self, task: dict, result: dict) -> tuple[bool, str]:
        """验证时效：是否在超时限制内完成"""
        total_time = result.get("total_time_seconds", 0)
        estimated_time = task.get("total_estimated_time", 0)
        
        if total_time > estimated_time:
            return False, f"任务超时: 实际{total_time}秒 > 预估{estimated_time}秒"
        return True, f"未超时 (实际{total_time}秒 <= 预估{estimated_time}秒)"
    
    def verify_error_free(self, result: dict) -> tuple[bool, str]:
        """验证无错误：检查是否有错误信息"""
        errors = []
        
        if result.get("status") == "failed":
            errors.append(f"任务状态为failed: {result.get('error', '未知错误')}")
        
        if "subtask_results" in result:
            for sr in result["subtask_results"]:
                if sr.get("status") == "failed":
                    errors.append(f"子任务失败: {sr.get('subtask_id')} - {sr.get('error', '未知')}")
        
        if result.get("exit_code", 0) != 0 and result.get("exit_code") is not None:
            errors.append(f"非零退出码: {result.get('exit_code')}")
        
        if errors:
            return False, "; ".join(errors)
        return True, "无错误"
    
    def verify(
        self, 
        task_id: str, 
        result: dict = None, 
        checks: dict = None,
        custom_validators: dict = None
    ) -> VerificationResult:
        """
        执行验证
        
        Args:
            task_id: 任务ID
            result: 执行结果（如果为None，从文件加载）
            checks: 要执行的检查项（默认为DEFAULT_CHECKS）
            custom_validators: 自定义验证器 {name: (task, result) -> (passed, message)}
        """
        # 加载任务定义
        task = self._load_task(task_id)
        
        # 加载结果
        if result is None:
            result = self._load_result(task_id)
        
        # 确定检查项
        if checks is None:
            checks = self.default_checks
        
        # 执行验证
        check_results = {}
        errors = []
        warnings = []
        
        # 1. 完整性检查
        if checks.get("completeness", False):
            passed, msg = self.verify_completeness(task, result)
            check_results["completeness"] = {"passed": passed, "message": msg}
            if not passed:
                errors.append(msg)
        
        # 2. 格式检查
        if checks.get("format", False):
            passed, msg = self.verify_format(result)
            check_results["format"] = {"passed": passed, "message": msg}
            if not passed:
                errors.append(msg)
        
        # 3. 超时检查
        if checks.get("timeout", False):
            passed, msg = self.verify_timeout(task, result)
            check_results["timeout"] = {"passed": passed, "message": msg}
            if not passed:
                errors.append(msg)
        
        # 4. 错误检查
        if checks.get("error_free", False):
            passed, msg = self.verify_error_free(result)
            check_results["error_free"] = {"passed": passed, "message": msg}
            if not passed:
                errors.append(msg)
        
        # 5. 自定义验证器
        if custom_validators:
            for name, validator in custom_validators.items():
                try:
                    passed, msg = validator(task, result)
                    check_results[name] = {"passed": passed, "message": msg}
                    if not passed:
                        errors.append(msg)
                except Exception as e:
                    check_results[name] = {"passed": False, "message": f"验证器执行出错: {str(e)}"}
                    errors.append(f"{name}验证器出错: {str(e)}")
        
        # 汇总结果
        vr = VerificationResult(
            task_id=task_id,
            passed=len(errors) == 0,
            checks=check_results,
            errors=errors,
            warnings=warnings,
            verified_at=datetime.now().isoformat()
        )
        
        return vr
    
    def save(self, result: VerificationResult, output_dir: str = None) -> str:
        """保存验证结果"""
        if output_dir is None:
            output_dir = Path.home() / ".hermes" / "repos" / "mochenhermes" / "tasks"
        
        output_path = Path(output_dir) / f"{result.task_id}_verification.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        
        return str(output_path)


def main():
    """命令行入口"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python task_verifier.py <任务ID>")
        print("示例: python task_verifier.py task_20260416185435_5600")
        return
    
    task_id = sys.argv[1]
    
    verifier = TaskVerifier()
    
    try:
        result = verifier.verify(task_id)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        
        # 保存结果
        output_path = verifier.save(result)
        print(f"\n验证结果已保存到: {output_path}")
        
        # 退出码
        sys.exit(0 if result.passed else 1)
        
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(2)
    except Exception as e:
        print(f"验证过程出错: {e}")
        sys.exit(3)


if __name__ == "__main__":
    main()
