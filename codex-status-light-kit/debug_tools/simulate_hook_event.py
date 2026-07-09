#!/usr/bin/env python3
"""Simulate a Codex hook event without opening Codex."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "codex_hooks" / "send_signal.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate a Codex hook event.")
    parser.add_argument("event", help="For example: UserPromptSubmit, PreToolUse, PermissionRequest, Stop")
    parser.add_argument("--failed", action="store_true", help="Mark a PostToolUse event as failed.")
    args = parser.parse_args()

    payload = {"event": args.event}
    if args.failed:
        payload["success"] = False

    completed = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
