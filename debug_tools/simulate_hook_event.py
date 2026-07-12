#!/usr/bin/env python3
"""Simulate a Codex hook event without opening Codex."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "codex_hooks" / "send_signal.py"
EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "SubagentStop",
    "Stop",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate a Codex hook event.")
    parser.add_argument("event", choices=EVENTS)
    parser.add_argument("--failed", action="store_true", help="Mark a PostToolUse event as failed.")
    parser.add_argument("--simulate", action="store_true", help="Write a log without opening serial.")
    args = parser.parse_args()

    payload = {"hook_event_name": args.event, "turn_id": "debug-turn"}
    if args.failed:
        payload["tool_response"] = {"metadata": {"exit_code": 1}}

    environment = os.environ.copy()
    if args.simulate:
        environment["STATUS_LIGHT_SIMULATE"] = "1"

    completed = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        check=False,
        env=environment,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
