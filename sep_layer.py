"""
SEPL — Self Evolution Protocol Layer: Propose → Assess → Commit with rollback.

Design (Autogenesis-style):
- Propose: Optimizer generates prompt refinements from memory
- Assess: Optional validation (e.g., run verification after apply)
- Commit: Apply proposals to configs/prompts/ with backup
- Rollback: Restore from backup if commit fails or is reverted

Usage:
  python sep_layer.py propose     # Run optimizer, output proposals
  python sep_layer.py commit      # Apply proposals (creates backup)
  python sep_layer.py rollback    # Restore from latest backup
  python sep_layer.py status      # Show last commit/backup state
"""

import os
import json
import sys
import glob
import shutil
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIGS_DIR = os.path.join(SCRIPT_DIR, "configs")
PROMPTS_DIR = os.path.join(CONFIGS_DIR, "prompts")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
SEPL_STATE_PATH = os.path.join(OUTPUT_DIR, "sep_layer_state.json")


def _load_state() -> dict:
    if not os.path.exists(SEPL_STATE_PATH):
        return {}
    try:
        with open(SEPL_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(SEPL_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def propose() -> dict:
    """Propose: Run optimizer to generate refinements from memory."""
    from optimizer_agent import run_optimizer
    return run_optimizer()


def assess(proposals: list) -> dict:
    """
    Assess: Validate proposals (e.g., check prompt files exist).
    Returns {valid: bool, errors: list}.
    """
    errors = []
    for p in proposals:
        name = p.get("prompt", "")
        if not name:
            errors.append("Proposal missing 'prompt' field")
        if not os.path.exists(os.path.join(PROMPTS_DIR, f"{name}.txt")):
            errors.append(f"Prompt file not found: {name}.txt")
    return {"valid": len(errors) == 0, "errors": errors}


def commit() -> dict:
    """
    Commit: Apply proposals to prompts. Creates backup.
    Returns {committed: int, backups: list, state: dict}.
    """
    from optimizer_agent import apply_proposals, run_optimizer


    # Ensure we have proposals
    proposals_path = os.path.join(OUTPUT_DIR, "optimizer_proposals.json")
    if not os.path.exists(proposals_path):
        run_optimizer()
    result = apply_proposals(dry_run=False)
    if result.get("applied", 0) == 0:
        return {"committed": 0, "backups": [], "state": _load_state()}

    state = {
        "last_commit": datetime.now().isoformat(),
        "backups": result.get("backups", []),
        "applied": result["applied"],
    }
    _save_state(state)
    return {"committed": result["applied"], "backups": result.get("backups", []), "state": state}


def rollback() -> dict:
    """
    Rollback: Restore prompts from latest backup.
    Returns {restored: int, from_backups: list}.
    """
    state = _load_state()
    backups = state.get("backups", [])
    if not backups:
        return {"restored": 0, "from_backups": [], "error": "No backups in state"}

    restored = 0
    for backup_path in backups:
        if not os.path.exists(backup_path):
            continue
        base = os.path.basename(backup_path)
        if ".backup." in base:
            target_name = base.split(".backup.")[0]
            target_path = os.path.join(PROMPTS_DIR, target_name)
            shutil.copy(backup_path, target_path)
            restored += 1

    _save_state({})  # Clear state after rollback
    return {"restored": restored, "from_backups": backups}


def status() -> dict:
    """Status: Show last commit and backup state."""
    state = _load_state()
    backups = glob.glob(os.path.join(PROMPTS_DIR, "*.backup.*.txt"))
    return {
        "last_commit": state.get("last_commit"),
        "last_applied": state.get("applied"),
        "backups_in_state": state.get("backups", []),
        "backups_on_disk": backups,
    }


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "propose"
    if cmd == "propose":
        report = propose()
        print(f"Proposals: {report['summary']}")
    elif cmd == "commit":
        result = commit()
        print(f"Committed: {result['committed']}. Backups: {result.get('backups', [])}")
    elif cmd == "rollback":
        result = rollback()
        print(f"Restored: {result['restored']} from {result.get('from_backups', [])}")
    elif cmd == "status":
        s = status()
        print(json.dumps(s, indent=2))
    else:
        print("Usage: python sep_layer.py [propose|commit|rollback|status]")
        sys.exit(1)


if __name__ == "__main__":
    main()
