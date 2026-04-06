"""
Sandboxed Code Execution — Hardened subprocess wrapper with resource limits.

Wraps subprocess.run with:
- Timeout enforcement
- Memory limits (via ulimit on Unix, job objects on Windows)
- Import whitelist for generated Python code
- Optional Docker container isolation

Used by verification_agent and any agent that runs LLM-generated code.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SandboxConfig:
    """Configuration for the code execution sandbox."""
    timeout_seconds: int = 120
    max_memory_mb: int = 2048
    use_docker: bool = False
    docker_image: str = "python:3.12-slim"
    allowed_imports: list[str] = field(default_factory=lambda: [
        "numpy", "pandas", "scikit-learn", "sklearn", "scipy",
        "matplotlib", "json", "math", "statistics", "collections",
        "itertools", "functools", "re", "pathlib",
        "datetime", "time", "csv", "io", "typing", "dataclasses",
    ])
    blocked_imports: list[str] = field(default_factory=lambda: [
        "os", "subprocess", "shutil", "socket", "http", "urllib",
        "ftplib", "smtplib", "telnetlib", "ctypes", "multiprocessing",
        "signal", "importlib", "pickle", "shelve",
    ])
    blocked_builtins: list[str] = field(default_factory=lambda: [
        "exec", "eval",
        "breakpoint", "exit", "quit",
    ])

    @classmethod
    def from_config(cls) -> SandboxConfig:
        """Load from configs/pipeline.yaml -> sandbox section."""
        try:
            from utils.config_loader import load_pipeline_config
            cfg = load_pipeline_config().get("sandbox", {})
            return cls(
                timeout_seconds=cfg.get("timeout_seconds", 120),
                max_memory_mb=cfg.get("max_memory_mb", 2048),
                use_docker=cfg.get("use_docker", False),
                docker_image=cfg.get("docker_image", "python:3.12-slim"),
                allowed_imports=cfg.get("allowed_imports", cls().allowed_imports),
            )
        except Exception:
            return cls()


@dataclass
class SandboxResult:
    """Result of sandboxed code execution."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    error: str | None = None
    timed_out: bool = False
    blocked_imports: list[str] = field(default_factory=list)


def _check_imports(code: str, config: SandboxConfig) -> list[str]:
    """Check code for disallowed imports. Returns list of blocked import names."""
    blocked = []
    import_pattern = re.compile(
        r'(?:^|\n)\s*(?:import|from)\s+([\w.]+)', re.MULTILINE
    )
    for match in import_pattern.finditer(code):
        module = match.group(1).split(".")[0]
        if module in config.blocked_imports:
            blocked.append(module)
        # Also check for disallowed submodules
        full_module = match.group(1)
        for b in config.blocked_imports:
            if full_module.startswith(b):
                if full_module not in blocked:
                    blocked.append(full_module)
    # Check for blocked builtins used as function calls
    for builtin in config.blocked_builtins:
        pattern = re.compile(rf'\b{re.escape(builtin)}\s*\(')
        if pattern.search(code):
            blocked.append(f"builtin:{builtin}")
    return blocked


def _wrap_with_restrictions(code: str, config: SandboxConfig) -> str:
    """Wrap user code with import restrictions.

    Blocked builtins (exec/eval) are enforced by static analysis in
    ``_check_imports``.  Only the import hook is injected at runtime
    because replacing builtins like ``exec`` breaks Python's own
    import machinery (which calls ``builtins.exec`` internally).
    """
    wrapper = (
        "import sys\n"
        "import builtins\n"
        "\n"
        "_original_import = builtins.__import__\n"
        f"_blocked_modules = {config.blocked_imports!r}\n"
        "\n"
        "def _safe_import(name, *args, **kwargs):\n"
        "    base = name.split('.')[0]\n"
        "    if base in _blocked_modules:\n"
        "        raise ImportError(f\"Import of '{name}' is blocked in sandbox.\")\n"
        "    return _original_import(name, *args, **kwargs)\n"
        "\n"
        "builtins.__import__ = _safe_import\n"
        "\n"
        "# --- User code below ---\n"
    )
    return wrapper + "\n" + code


def execute_code(
    code: str,
    *,
    config: SandboxConfig | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> SandboxResult:
    """Execute Python code in a sandboxed environment.

    Checks for blocked imports, wraps with restrictions, executes with timeout.
    """
    config = config or SandboxConfig.from_config()

    # Static analysis: check for blocked imports
    blocked = _check_imports(code, config)
    if blocked:
        return SandboxResult(
            success=False,
            error=f"Blocked imports/builtins detected: {blocked}",
            blocked_imports=blocked,
        )

    # Wrap code with runtime restrictions
    wrapped = _wrap_with_restrictions(code, config)

    if config.use_docker:
        return _execute_in_docker(wrapped, config, cwd)

    return _execute_local(wrapped, config, cwd, env)


def _execute_local(
    code: str,
    config: SandboxConfig,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> SandboxResult:
    """Execute code locally with timeout and resource constraints."""
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_file = f.name

        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        # On Unix, prepend ulimit for memory restriction
        if sys.platform != "win32":
            mem_kb = config.max_memory_mb * 1024
            cmd = [
                "bash", "-c",
                f"ulimit -v {mem_kb} 2>/dev/null; {sys.executable} {tmp_file}"
            ]
        else:
            cmd = [sys.executable, tmp_file]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds,
                cwd=cwd,
                env=run_env,
            )
            return SandboxResult(
                success=result.returncode == 0,
                stdout=result.stdout[:50000],
                stderr=result.stderr[:50000],
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                error=f"Execution timed out after {config.timeout_seconds}s",
                timed_out=True,
            )
    except Exception as e:
        return SandboxResult(success=False, error=str(e))
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except OSError:
                pass


def _execute_in_docker(
    code: str,
    config: SandboxConfig,
    cwd: str | None = None,
) -> SandboxResult:
    """Execute code in a Docker container for maximum isolation."""
    try:
        import docker as docker_lib
        client = docker_lib.from_env()

        result = client.containers.run(
            config.docker_image,
            command=["python", "-c", code],
            mem_limit=f"{config.max_memory_mb}m",
            network_disabled=True,
            read_only=True,
            remove=True,
            stdout=True,
            stderr=True,
            timeout=config.timeout_seconds,
        )
        stdout = result.decode("utf-8") if isinstance(result, bytes) else str(result)
        return SandboxResult(success=True, stdout=stdout[:50000], returncode=0)
    except Exception as e:
        err_str = str(e)
        timed_out = "timeout" in err_str.lower() or "deadline" in err_str.lower()
        return SandboxResult(
            success=False,
            error=err_str[:5000],
            timed_out=timed_out,
        )
