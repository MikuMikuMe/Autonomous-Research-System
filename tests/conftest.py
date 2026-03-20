from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast


TESTS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_ROOT.parent
RUNTIME_FIXTURE_ROOT = TESTS_ROOT / "fixtures" / "runtime"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def runtime_fixture_dir(name: str) -> Path:
    return RUNTIME_FIXTURE_ROOT / name


def load_runtime_json(name: str, relative_path: str = "session.json") -> dict[str, object]:
    path = runtime_fixture_dir(name) / relative_path
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def load_runtime_text(name: str, relative_path: str) -> str:
    path = runtime_fixture_dir(name) / relative_path
    return path.read_text(encoding="utf-8")
