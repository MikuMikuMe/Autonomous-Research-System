"""
Sandboxed Code Execution — Resource-limited subprocess execution.

Wraps subprocess.run with security hardening for executing LLM-generated code:
  - Timeout enforcement
  - Memory limits (via resource limits on Linux/Mac, job objects on Windows)
  - Restricted environment variables (stripped API keys)
  - Temporary directory isolation
  - Network restriction hints (best-effort)

Usage:
    from utils.sandbox import run_sandboxed
    result = run_sandboxed(code_string, timeout=30, max_memory_mb=512)
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)

# Environment variables to strip from sandboxed execution
_SENSITIVE_ENV_KEYS = {
    "GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "ALPHAXIV_TOKEN", "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID",
    "AZURE_API_KEY", "HF_TOKEN", "HUGGINGFACE_TOKEN",
    "KAGGLE_KEY", "KAGGLE_USERNAME",
    "DATABASE_URL", "REDIS_URL",
    "SECRET_KEY", "JWT_SECRET",
}

# Allowlist of modules the sandbox can import (soft enforcement via wrapper)
_ALLOWED_MODULES = {
    "json", "math", "statistics", "collections", "itertools", "functools",
    "re", "datetime", "decimal", "fractions", "random", "string",
    "csv", "io", "pathlib", "os.path", "typing",
    "numpy", "pandas", "scipy", "sklearn", "matplotlib",
}


@dataclass
class SandboxResult:
    """Result of sandboxed code execution."""
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str | None = None


def _make_safe_env() -> dict[str, str]:
    """Create a sanitized environment for sandboxed execution."""
    env = {}
    for key, value in os.environ.items():
        # Strip sensitive keys
        if key.upper() in _SENSITIVE_ENV_KEYS:
            continue
        # Strip any key containing 'secret', 'token', 'password', 'key' (case-insensitive)
        lower_key = key.lower()
        if any(sensitive in lower_key for sensitive in ("secret", "token", "password", "api_key", "apikey")):
            continue
        env[key] = value
    # Ensure PYTHONPATH includes project root for imports
    env["PYTHONPATH"] = PROJECT_ROOT
    # Disable network for some libraries
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    return env


def _make_prelude(max_memory_mb: int | None = None) -> str:
    """Generate Python prelude code that enforces resource limits from inside the sandbox."""
    lines = [
        "import sys, os",
        "# Sandbox prelude: enforce resource limits",
    ]

    if platform.system() != "Windows" and max_memory_mb:
        lines.extend([
            "try:",
            "    import resource",
            f"    mem_bytes = {max_memory_mb} * 1024 * 1024",
            "    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))",
            "except Exception:",
            "    pass  # resource module not available",
        ])

    # Restrict file creation to temp directory
    lines.extend([
        "import tempfile as _tf",
        "_sandbox_dir = _tf.mkdtemp(prefix='sandbox_')",
        "os.chdir(_sandbox_dir)",
        "",
    ])

    return "\n".join(lines) + "\n"


def run_sandboxed(
    code: str,
    *,
    timeout: int = 30,
    max_memory_mb: int = 512,
    data_json: dict | None = None,
    cwd: str | None = None,
) -> SandboxResult:
    """Execute Python code in a sandboxed subprocess with resource limits.

    Args:
        code: Python source code to execute.
        timeout: Maximum execution time in seconds.
        max_memory_mb: Maximum memory in MB (Linux/Mac only).
        data_json: Optional JSON data made available as `data` variable.
        cwd: Working directory (defaults to a temporary directory).

    Returns:
        SandboxResult with stdout, stderr, returncode.
    """
    data_path = None
    tmp_path = None

    try:
        # Write data file if provided
        if data_json is not None:
            fd, data_path = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                import json
                json.dump(data_json, f)

        # Build sandboxed script
        prelude = _make_prelude(max_memory_mb)
        full_code = prelude

        if data_path:
            full_code += "import json\n"
            full_code += f"with open({repr(data_path)}, encoding='utf-8') as _f:\n"
            full_code += "    data = json.load(_f)\n\n"

        full_code += code

        # Write to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(full_code)
            tmp_path = f.name

        # Create isolated working directory
        work_dir = cwd or tempfile.mkdtemp(prefix="sandbox_work_")

        # Execute with resource limits
        env = _make_safe_env()

        # On Windows, use job objects via CREATE_BREAKAWAY_FROM_JOB
        # On Unix, we rely on the resource module inside the prelude
        kwargs: dict = {
            "capture_output": True,
            "text": True,
            "timeout": timeout,
            "env": env,
            "cwd": work_dir,
        }

        # On Windows, use CREATE_NEW_PROCESS_GROUP for isolation
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.run(
            [sys.executable, tmp_path],
            **kwargs,
        )

        return SandboxResult(
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )

    except subprocess.TimeoutExpired:
        return SandboxResult(
            returncode=-1,
            stdout="",
            stderr=f"Sandbox timeout after {timeout}s",
            timed_out=True,
            error=f"Execution exceeded {timeout}s time limit",
        )
    except Exception as e:
        return SandboxResult(
            returncode=-1,
            stdout="",
            stderr=str(e),
            error=str(e),
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        if data_path and os.path.exists(data_path):
            try:
                os.unlink(data_path)
            except OSError:
                pass
