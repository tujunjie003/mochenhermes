#!/usr/bin/env python3
"""
自愈引擎 (Self-Healing Engine)
任务失败时自动尝试修复

功能：
1. 常见错误自动修复
2. 失败策略切换
3. 回退到备选方案
4. 错误模式学习
"""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class HealResult:
    """自愈结果"""
    healed: bool
    method: str  # 使用什么方法修复
    new_command: str = None
    error: str = None
    attempts: int = 0


class ErrorPattern:
    """错误模式"""
    
    # 文件相关
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION_DENIED = "permission_denied"
    IS_A_DIRECTORY = "is_a_directory"
    
    # 网络相关
    NETWORK_TIMEOUT = "network_timeout"
    CONNECTION_FAILED = "connection_failed"
    
    # Git相关
    GIT_CONFLICT = "git_conflict"
    GIT_AUTH_FAILED = "git_auth_failed"
    
    # 命令相关
    COMMAND_NOT_FOUND = "command_not_found"
    SYNTAX_ERROR = "syntax_error"
    
    # 通用
    UNKNOWN = "unknown"


class SelfHealingEngine:
    """自愈引擎"""
    
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = Path.home() / ".hermes" / "repos" / "mochenhermes"
        self.base_dir = Path(base_dir)
        self.logs_dir = self.base_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def _log(self, level: str, message: str) -> None:
        """记录日志"""
        log_file = self.logs_dir / f"healing_{datetime.now().strftime('%Y%m%d')}.log"
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    
    def classify_error(self, error: str, command: str = "") -> str:
        """分类错误类型"""
        error_lower = error.lower()
        
        # 文件相关
        if "is a directory" in error_lower:
            return ErrorPattern.IS_A_DIRECTORY
        
        if "no such file" in error_lower or ("not found" in error_lower and "command not found" not in error_lower):
            return ErrorPattern.FILE_NOT_FOUND
        
        if "permission denied" in error_lower or "access denied" in error_lower:
            return ErrorPattern.PERMISSION_DENIED
        
        # 网络相关
        if "timeout" in error_lower or "timed out" in error_lower:
            return ErrorPattern.NETWORK_TIMEOUT
        
        if "connection" in error_lower and ("failed" in error_lower or "refused" in error_lower):
            return ErrorPattern.CONNECTION_FAILED
        
        # Git相关
        if "conflict" in error_lower or "merge conflict" in error_lower:
            return ErrorPattern.GIT_CONFLICT
        
        if "authentication" in error_lower or "auth" in error_lower:
            return ErrorPattern.GIT_AUTH_FAILED
        
        # 命令相关
        if "command not found" in error_lower:
            return ErrorPattern.COMMAND_NOT_FOUND
        
        if "syntax error" in error_lower or "invalid syntax" in error_lower:
            return ErrorPattern.SYNTAX_ERROR
        
        return ErrorPattern.UNKNOWN
    
    def heal(
        self,
        error: str,
        command: str,
        tool: str = "terminal",
        context: dict = None
    ) -> HealResult:
        """
        尝试修复错误
        
        Args:
            error: 错误信息
            command: 失败的命令
            tool: 使用的工具
            context: 额外上下文信息
        
        Returns:
            HealResult: 修复结果
        """
        context = context or {}
        error_type = self.classify_error(error, command)
        
        self._log("INFO", f"尝试修复错误: type={error_type}, cmd={command[:50]}...")
        
        # 根据错误类型选择修复方法
        if error_type == ErrorPattern.FILE_NOT_FOUND:
            return self._heal_file_not_found(command, context)
        
        elif error_type == ErrorPattern.PERMISSION_DENIED:
            return self._heal_permission_denied(command, context)
        
        elif error_type == ErrorPattern.IS_A_DIRECTORY:
            return self._heal_is_directory(command, context)
        
        elif error_type == ErrorPattern.NETWORK_TIMEOUT:
            return self._heal_network_timeout(command, context)
        
        elif error_type == ErrorPattern.COMMAND_NOT_FOUND:
            return self._heal_command_not_found(command, context)
        
        elif error_type == ErrorPattern.SYNTAX_ERROR:
            return self._heal_syntax_error(command, context)
        
        else:
            return self._heal_unknown(command, error, context)
    
    def _heal_file_not_found(self, command: str, context: dict) -> HealResult:
        """修复文件不存在错误"""
        # 尝试从命令中提取文件路径
        path_match = re.search(r"['\"](.+?)['\"]|(\S+\.(?:py|yaml|json|md|txt|sh))", command)
        if not path_match:
            return HealResult(healed=False, method="none", error="无法提取文件路径")
        
        file_path = path_match.group(1) or path_match.group(2)
        
        # 检查文件是否在base_dir下
        if not file_path.startswith("/"):
            # 尝试在base_dir下查找
            potential_paths = [
                self.base_dir / file_path,
                self.base_dir / "scripts" / file_path,
                self.base_dir / "config" / file_path,
                self.base_dir / "tasks" / file_path,
            ]
            
            for p in potential_paths:
                if p.exists():
                    new_command = command.replace(file_path, str(p))
                    self._log("INFO", f"路径修正: {file_path} -> {p}")
                    return HealResult(
                        healed=True,
                        method="path_correction",
                        new_command=new_command
                    )
        
        # 尝试ls看看到底有什么
        parent = str(Path(file_path).parent)
        if parent and parent != ".":
            try:
                result = subprocess.run(
                    f"ls -la {parent}",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                self._log("INFO", f"目录内容: {result.stdout[:200]}")
            except Exception:
                pass
        
        return HealResult(healed=False, method="file_not_found", error=f"文件不存在: {file_path}")
    
    def _heal_permission_denied(self, command: str, context: dict) -> HealResult:
        """修复权限错误"""
        path_match = re.search(r"['\"](.+?)['\"]|(\S+)", command)
        if path_match:
            file_path = path_match.group(1) or path_match.group(2)
            
            # 尝试chmod
            new_cmd = command
            
            # 如果是写入操作，检查目录权限
            if "write" in command.lower() or ">" in command:
                parent = Path(file_path).parent
                try:
                    subprocess.run(f"chmod 755 {parent}", shell=True, timeout=5)
                    self._log("INFO", f"目录权限已修复: {parent}")
                except Exception:
                    pass
            
            return HealResult(
                healed=False,
                method="permission_denied",
                error=f"权限不足: {file_path}，可能需要手动处理"
            )
        
        return HealResult(healed=False, method="permission_denied", error="权限错误")
    
    def _heal_is_directory(self, command: str, context: dict) -> HealResult:
        """修复误把目录当文件用的错误"""
        path_match = re.search(r"['\"](.+?)['\"]|(\S+)", command)
        if not path_match:
            return HealResult(healed=False, method="none", error="无法提取路径")
        
        file_path = path_match.group(1) or path_match.group(2)
        
        # 如果是cat/wc等命令，改用ls
        if any(cmd in command for cmd in ["cat", "wc", "head", "tail"]):
            new_command = command.replace("cat", "ls").replace("wc", "ls")
            
            # 简单替换第一个文件参数为目录名
            if file_path:
                new_command = f"ls {file_path}/"
            
            self._log("INFO", f"目录/文件修正: cat/wc -> ls")
            return HealResult(
                healed=True,
                method="directory_vs_file",
                new_command=new_command
            )
        
        return HealResult(healed=False, method="is_directory", error=f"路径是目录: {file_path}")
    
    def _heal_network_timeout(self, command: str, context: dict) -> HealResult:
        """修复网络超时"""
        # 检查是否有curl/wget
        if "curl" in command:
            # 添加超时参数
            new_command = re.sub(r"--max-time \d+", "", command)
            new_command = new_command.strip() + " --max-time 30"
            
            self._log("INFO", "网络超时修复: 添加 --max-time 30")
            return HealResult(
                healed=True,
                method="timeout_extension",
                new_command=new_command
            )
        
        # 对于git clone，尝试shallow clone
        if "git clone" in command:
            new_command = command.replace("git clone", "git clone --depth 1")
            self._log("INFO", "Git clone优化: 使用浅克隆")
            return HealResult(
                healed=True,
                method="shallow_clone",
                new_command=new_command
            )
        
        return HealResult(
            healed=False,
            method="network_timeout",
            error="网络超时，建议检查网络或使用代理"
        )
    
    def _heal_command_not_found(self, command: str, context: dict) -> HealResult:
        """修复命令不存在"""
        cmd_match = re.match(r"^(\S+)", command.strip())
        if not cmd_match:
            return HealResult(healed=False, method="none", error="无法识别命令")
        
        cmd = cmd_match.group(1)
        
        # 常见命令映射
        aliases = {
            "python": "python3",
            "pip": "pip3",
            "node": "nodejs",
        }
        
        if cmd in aliases:
            new_command = command.replace(cmd, aliases[cmd], 1)
            self._log("INFO", f"命令别名修正: {cmd} -> {aliases[cmd]}")
            return HealResult(
                healed=True,
                method="command_alias",
                new_command=new_command
            )
        
        return HealResult(
            healed=False,
            method="command_not_found",
            error=f"命令不存在: {cmd}"
        )
    
    def _heal_syntax_error(self, command: str, context: dict) -> HealResult:
        """修复语法错误"""
        # 常见Python语法错误修复
        if command.strip().endswith(".py") or "python" in command.lower():
            # 检查常见错误
            if "print " in command and "print(" not in command:
                # Python 2 -> Python 3 print
                new_command = re.sub(r"print\s+(['\"])", r"print(\1", command)
                new_command = re.sub(r"print\s+(\w+)", r"print(\1)", new_command)
                self._log("INFO", "语法修复: print -> print()")
                return HealResult(
                    healed=True,
                    method="python2_to_python3",
                    new_command=new_command
                )
        
        return HealResult(
            healed=False,
            method="syntax_error",
            error="语法错误，需要手动修复"
        )
    
    def _heal_unknown(self, command: str, error: str, context: dict) -> HealResult:
        """处理未知错误"""
        # 记录错误供后续分析
        error_record = {
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "error": error,
            "context": context
        }
        
        error_log = self.logs_dir / "unknown_errors.json"
        errors = []
        if error_log.exists():
            try:
                with open(error_log, 'r', encoding='utf-8') as f:
                    errors = json.load(f)
            except Exception:
                pass
        
        errors.append(error_record)
        
        # 只保留最近100条
        errors = errors[-100:]
        
        with open(error_log, 'w', encoding='utf-8') as f:
            json.dump(errors, f, ensure_ascii=False, indent=2)
        
        self._log("WARN", f"未知错误已记录: {error[:50]}...")
        
        return HealResult(
            healed=False,
            method="unknown",
            error=error
        )
    
    def heal_with_strategy(
        self,
        command: str,
        error: str,
        tool: str = "terminal",
        context: dict = None,
        max_attempts: int = 2
    ) -> tuple[bool, str]:
        """
        使用多种策略尝试修复
        
        Returns:
            (修复成功, 最终命令)
        """
        current_command = command
        current_error = error
        
        for attempt in range(max_attempts):
            result = self.heal(current_error, current_command, tool, context)
            
            if result.healed and result.new_command:
                # 验证修复是否有效
                self._log("INFO", f"尝试修复 (attempt {attempt + 1}): {result.method}")
                
                # 检查新命令是否不同
                if result.new_command != current_command:
                    current_command = result.new_command
                    # 继续循环，让heal基于新的错误信息再次尝试
                    continue
                else:
                    return True, current_command
            else:
                if attempt < max_attempts - 1:
                    # 尝试其他方法，继续循环
                    current_error = result.error or error
                    continue
                else:
                    break
        
        return result.healed, current_command if result.healed else command
    
    def get_failure_patterns(self, limit: int = 10) -> list:
        """获取失败模式统计"""
        error_log = self.logs_dir / "unknown_errors.json"
        
        if not error_log.exists():
            return []
        
        try:
            with open(error_log, 'r', encoding='utf-8') as f:
                errors = json.load(f)
            
            # 统计错误类型
            patterns = {}
            for e in errors[-100:]:
                err = e.get("error", "")[:50]
                patterns[err] = patterns.get(err, 0) + 1
            
            # 排序返回
            sorted_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)
            return [{"error": k, "count": v} for k, v in sorted_patterns[:limit]]
        except Exception:
            return []


def main():
    """测试自愈引擎"""
    engine = SelfHealingEngine()
    
    test_cases = [
        ("cat /nonexistent/file.txt", "cat: /nonexistent/file.txt: No such file or directory"),
        ("python script.py", "python: command not found"),
        ("curl https://example.com", "curl: (7) Failed to connect to example.com: Connection refused"),
        ("git clone https://github.com/somerepo.git", "fatal: unable to access 'https://github.com/somerepo.git/': Timeout"),
    ]
    
    print("自愈引擎测试:\n")
    for cmd, err in test_cases:
        error_type = engine.classify_error(err, cmd)
        result = engine.heal(err, cmd)
        print(f"错误: {err[:50]}...")
        print(f"类型: {error_type}")
        print(f"修复: {'是' if result.healed else '否'} ({result.method})")
        if result.new_command:
            print(f"新命令: {result.new_command}")
        print()


if __name__ == "__main__":
    main()
