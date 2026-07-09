#!/usr/bin/env python3
"""Codex lifecycle hook -> serial status light.

The script is intentionally quiet on stdout so it does not interfere with
Codex hook handling. Diagnostics go to stderr and to logs/status_light.log.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import serial
    import serial.tools.list_ports
except Exception:  # pragma: no cover - handled at runtime for friendlier setup.
    serial = None


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = ROOT / "logs"
DEFAULT_MAPPING_FILE = Path(__file__).resolve().parent / "hook_mapping.json"

VALID_STATES = {
    "IDLE",
    "THINKING",
    "WAITING_USER",
    "TASK_COMPLETE",
    "TASK_FAILED",
    "TOOL_ERROR",
}

DEFAULT_BAUD = 115200
DEFAULT_DEBOUNCE_SECONDS = 0.4


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def log(message: str) -> None:
    log_dir = Path(os.getenv("STATUS_LIGHT_LOG_DIR", str(DEFAULT_LOG_DIR)))
    log_dir.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " | " + message
    print(line, file=sys.stderr)
    try:
        with (log_dir / "status_light.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_mapping() -> dict[str, str]:
    mapping_file = Path(os.getenv("STATUS_LIGHT_MAPPING", str(DEFAULT_MAPPING_FILE)))
    try:
        data = json.loads(mapping_file.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()}
    except Exception as exc:
        log(f"mapping load failed: {exc}")
        return {}


def find_hook_event(payload: dict[str, Any]) -> str:
    for key in ("event", "hook_event_name", "event_name", "hookEventName"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    params = payload.get("params")
    if isinstance(params, dict):
        for key in ("event", "hook_event_name", "event_name", "hookEventName"):
            value = params.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def nested_values(payload: Any) -> list[Any]:
    values: list[Any] = []
    if isinstance(payload, dict):
        for value in payload.values():
            values.append(value)
            values.extend(nested_values(value))
    elif isinstance(payload, list):
        for value in payload:
            values.append(value)
            values.extend(nested_values(value))
    return values


def post_tool_use_failed(payload: dict[str, Any]) -> bool:
    """Best-effort failure detection across Codex versions and hook payloads."""
    candidates = [payload] + [v for v in nested_values(payload) if isinstance(v, dict)]
    for obj in candidates:
        for key in ("success", "ok"):
            if obj.get(key) is False:
                return True
        for key in ("exit_code", "exitCode", "returncode", "return_code"):
            value = obj.get(key)
            if isinstance(value, int) and value != 0:
                return True
        for key in ("status", "state", "outcome", "result"):
            value = obj.get(key)
            if isinstance(value, str) and value.lower() in {"failed", "failure", "error", "errored"}:
                return True
        if obj.get("error") or obj.get("exception"):
            return True
    return False


def choose_state(event: str, payload: dict[str, Any], mapping: dict[str, str]) -> str | None:
    if event == "PostToolUse" and post_tool_use_failed(payload):
        return mapping.get("PostToolUse.failure", "TOOL_ERROR")
    state = mapping.get(event)
    if state in VALID_STATES:
        return state
    return None


def session_flag() -> Path:
    log_dir = Path(os.getenv("STATUS_LIGHT_LOG_DIR", str(DEFAULT_LOG_DIR)))
    return log_dir / "session_active.flag"


def update_session_flag(event: str) -> None:
    flag = session_flag()
    flag.parent.mkdir(parents=True, exist_ok=True)
    if event in {"SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest"}:
        flag.write_text("1", encoding="utf-8")
    elif event == "Stop":
        try:
            flag.unlink()
        except FileNotFoundError:
            pass


def should_debounce(event: str, state: str) -> bool:
    if event not in {"PreToolUse", "PostToolUse"}:
        return False
    try:
        interval = float(os.getenv("STATUS_LIGHT_DEBOUNCE_SECONDS", str(DEFAULT_DEBOUNCE_SECONDS)))
    except ValueError:
        interval = DEFAULT_DEBOUNCE_SECONDS
    if interval <= 0:
        return False

    marker = Path(os.getenv("STATUS_LIGHT_LOG_DIR", str(DEFAULT_LOG_DIR))) / ".last_send.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    try:
        old = json.loads(marker.read_text(encoding="utf-8"))
        if old.get("state") == state and now - float(old.get("time", 0)) < interval:
            return True
    except Exception:
        pass
    marker.write_text(json.dumps({"state": state, "time": now}), encoding="utf-8")
    return False


def find_serial_port() -> str | None:
    forced = os.getenv("STATUS_LIGHT_PORT")
    if forced:
        return forced
    if serial is None:
        return None

    ports = list(serial.tools.list_ports.comports())
    preferred_vid_pid = {
        (0x10C4, 0xEA60),  # CP210x
        (0x1A86, 0x7523),  # CH340
    }

    for port in ports:
        if port.vid is not None and port.pid is not None and (port.vid, port.pid) in preferred_vid_pid:
            return port.device

    keywords = ("cp210", "ch340", "usb serial", "uart", "silicon labs")
    for port in ports:
        description = (port.description or "").lower()
        if any(keyword in description for keyword in keywords):
            return port.device

    return ports[0].device if len(ports) == 1 else None


def send_state(state: str) -> bool:
    simulate = env_bool("STATUS_LIGHT_SIMULATE", False)
    if simulate:
        log(f"simulate send: {state}")
        return True

    if serial is None:
        log("pyserial is not installed. Run: python -m pip install -r codex_hooks/requirements.txt")
        return False

    port = find_serial_port()
    if not port:
        log("no serial port found. Set STATUS_LIGHT_PORT, for example: setx STATUS_LIGHT_PORT COM5")
        return False

    try:
        baud = int(os.getenv("STATUS_LIGHT_BAUD", str(DEFAULT_BAUD)))
    except ValueError:
        baud = DEFAULT_BAUD

    try:
        with serial.Serial(port, baud, timeout=2) as ser:
            ser.write((json.dumps({"state": state}) + "\n").encode("utf-8"))
            ser.flush()
            time.sleep(0.08)
            while ser.in_waiting:
                ser.readline()
        log(f"sent {state} to {port}")
        return True
    except Exception as exc:
        log(f"serial send failed: {exc}")
        return False


def handle_payload(payload: dict[str, Any]) -> int:
    event = find_hook_event(payload)
    if not event:
        log("ignored payload without event name")
        return 0

    mapping = load_mapping()
    state = choose_state(event, payload, mapping)
    update_session_flag(event)

    if not state:
        log(f"ignored event: {event}")
        return 0
    if should_debounce(event, state):
        log(f"debounced {event} -> {state}")
        return 0

    send_state(state)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Codex hook status to a serial traffic light.")
    parser.add_argument("--state", choices=sorted(VALID_STATES), help="Send one state directly.")
    parser.add_argument("--event", help="Simulate a hook event name.")
    parser.add_argument("--simulate", action="store_true", help="Log instead of writing to serial.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.simulate:
        os.environ["STATUS_LIGHT_SIMULATE"] = "1"

    if args.state:
        send_state(args.state)
        return 0
    if args.event:
        return handle_payload({"event": args.event})

    raw = sys.stdin.read()
    if not raw.strip():
        return 0

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        log(f"invalid hook json: {exc}")
        return 0
    if not isinstance(payload, dict):
        log("ignored non-object hook payload")
        return 0
    return handle_payload(payload)


if __name__ == "__main__":
    raise SystemExit(main())
