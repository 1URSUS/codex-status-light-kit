#!/usr/bin/env python3
"""Manually send one status to the traffic light."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "codex_hooks"))

from send_signal import VALID_STATES, send_state  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a state to the Codex status light.")
    parser.add_argument("state", choices=sorted(VALID_STATES))
    args = parser.parse_args()
    ok = send_state(args.state)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
