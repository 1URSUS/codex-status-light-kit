#!/usr/bin/env python3
"""Translate Codex lifecycle hook events into serial status-light commands."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # pragma: no cover - handled at runtime with a setup hint.
    serial = None


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
DEFAULT_DEBOUNCE_SECONDS = 0.6
DEFAULT_LOCK_TIMEOUT_SECONDS = 4.0
DEFAULT_SERIAL_RETRIES = 3
DEFAULT_LOG_MAX_BYTES = 1_000_000


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def default_log_dir() -> Path:
    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "codex-status-light-kit" / "logs"
    if os.getenv("XDG_STATE_HOME"):
        return Path(os.environ["XDG_STATE_HOME"]) / "codex-status-light-kit"
    return Path.home() / ".local" / "state" / "codex-status-light-kit"


def runtime_dir() -> Path:
    return Path(os.getenv("STATUS_LIGHT_LOG_DIR", str(default_log_dir())))


def _rotate_log(path: Path) -> None:
    if not path.exists() or path.stat().st_size < DEFAULT_LOG_MAX_BYTES:
        return
    backup = path.with_suffix(path.suffix + ".1")
    try:
        backup.unlink()
    except FileNotFoundError:
        pass
    path.replace(backup)


def log(message: str, *, error: bool = False) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " | " + message
    if error or env_bool("STATUS_LIGHT_VERBOSE"):
        print(line, file=sys.stderr)

    try:
        directory = runtime_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "status_light.log"
        _rotate_log(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        if not error:
            print(f"Status light logging failed: {exc}", file=sys.stderr)


def load_mapping() -> dict[str, str]:
    mapping_file = Path(os.getenv("STATUS_LIGHT_MAPPING", str(DEFAULT_MAPPING_FILE)))
    try:
        data = json.loads(mapping_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("mapping root must be an object")
        return {str(key): str(value) for key, value in data.items()}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        log(f"mapping load failed: {exc}", error=True)
        return {}


def find_hook_event(payload: dict[str, Any]) -> str:
    for key in ("hook_event_name", "event", "event_name", "hookEventName"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    params = payload.get("params")
    if isinstance(params, dict):
        for key in ("hook_event_name", "event", "event_name", "hookEventName"):
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
    """Best-effort failure detection using the documented tool_response field."""
    response = payload.get("tool_response", payload)
    candidates = [response] + [
        value for value in nested_values(response) if isinstance(value, dict)
    ]
    for obj in candidates:
        if not isinstance(obj, dict):
            continue
        for key in ("success", "ok"):
            if obj.get(key) is False:
                return True
        for key in ("exit_code", "exitCode", "returncode", "return_code"):
            value = obj.get(key)
            if isinstance(value, int) and value != 0:
                return True
        for key in ("status", "state", "outcome", "result"):
            value = obj.get(key)
            if isinstance(value, str) and value.lower() in {
                "failed",
                "failure",
                "error",
                "errored",
            }:
                return True
        if obj.get("error") or obj.get("exception"):
            return True
    return False


def choose_state(
    event: str, payload: dict[str, Any], mapping: dict[str, str]
) -> str | None:
    if event == "PostToolUse" and post_tool_use_failed(payload):
        return mapping.get("PostToolUse.failure", "TOOL_ERROR")
    state = mapping.get(event)
    if state in VALID_STATES:
        return state
    return None


def _port_description(port: Any) -> str:
    return " ".join(
        str(value or "")
        for value in (
            getattr(port, "description", ""),
            getattr(port, "manufacturer", ""),
            getattr(port, "hwid", ""),
        )
    ).lower()


def available_serial_ports() -> list[Any]:
    if serial is None:
        return []
    return list(serial.tools.list_ports.comports())


def find_serial_port(ports: Sequence[Any] | None = None) -> str | None:
    forced = os.getenv("STATUS_LIGHT_PORT")
    if forced:
        return forced.strip()
    if serial is None and ports is None:
        return None

    candidates = list(ports) if ports is not None else available_serial_ports()
    non_bluetooth = [
        port
        for port in candidates
        if "bluetooth" not in _port_description(port)
        and "bth" not in _port_description(port)
    ]

    # Silicon Labs CP210x and WCH CH34x/CH91xx families.
    preferred_vendors = {0x10C4, 0x1A86}
    for port in non_bluetooth:
        if getattr(port, "vid", None) in preferred_vendors:
            return str(port.device)

    keywords = (
        "cp210",
        "silicon labs",
        "ch340",
        "ch341",
        "ch343",
        "ch910",
        "wch",
        "usb serial",
        "usb-serial",
        "usb2.0-serial",
        "uart bridge",
    )
    for port in non_bluetooth:
        if any(keyword in _port_description(port) for keyword in keywords):
            return str(port.device)

    usb_ports = [
        port
        for port in non_bluetooth
        if getattr(port, "vid", None) is not None
        and getattr(port, "pid", None) is not None
    ]
    return str(usb_ports[0].device) if len(usb_ports) == 1 else None


@contextmanager
def serial_lock() -> Iterator[None]:
    """Serialize hook processes so only one opens the COM port at a time."""
    directory = runtime_dir()
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / "serial.lock"
    timeout = env_float(
        "STATUS_LIGHT_LOCK_TIMEOUT", DEFAULT_LOCK_TIMEOUT_SECONDS, minimum=0.1
    )
    deadline = time.monotonic() + timeout
    handle = lock_path.open("a+b")
    locked = False

    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            while not locked:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("timed out waiting for the serial lock")
                    time.sleep(0.05)
        else:
            import fcntl

            while not locked:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("timed out waiting for the serial lock")
                    time.sleep(0.05)

        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _last_send_marker() -> Path:
    return runtime_dir() / ".last_send.json"


def was_recently_sent(state: str) -> bool:
    interval = env_float(
        "STATUS_LIGHT_DEBOUNCE_SECONDS", DEFAULT_DEBOUNCE_SECONDS
    )
    if interval <= 0:
        return False
    try:
        previous = json.loads(_last_send_marker().read_text(encoding="utf-8"))
        elapsed = time.time() - float(previous.get("time", 0))
        return (
            previous.get("state") == state
            and 0 <= elapsed < interval
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def record_send(state: str) -> None:
    marker = _last_send_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker.with_name(f"{marker.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps({"state": state, "time": time.time()}), encoding="utf-8"
    )
    temporary.replace(marker)


def _write_state_with_ack(port: str, baud: int, state: str) -> bool:
    attempts = env_int("STATUS_LIGHT_SERIAL_RETRIES", DEFAULT_SERIAL_RETRIES)
    payload = (json.dumps({"state": state}) + "\n").encode("utf-8")
    last_error: Exception | None = None

    for attempt in range(attempts):
        connection = None
        try:
            connection = serial.Serial()
            connection.port = port
            connection.baudrate = baud
            connection.timeout = 0.2
            connection.write_timeout = 2

            # Configure these before open to avoid pulsing a NodeMCU auto-reset circuit.
            connection.dtr = False
            connection.rts = False
            connection.open()
            connection.reset_input_buffer()

            for _ in range(2):
                connection.write(payload)
                connection.flush()
                deadline = time.monotonic() + 0.8
                while time.monotonic() < deadline:
                    reply = connection.readline().decode("utf-8", errors="replace").strip()
                    if reply == f"State: {state}":
                        return True
                time.sleep(0.1)
            last_error = RuntimeError("device did not acknowledge the command")
        except Exception as exc:  # Serial backends raise several platform errors.
            last_error = exc
        finally:
            if connection is not None and connection.is_open:
                connection.close()

        if attempt + 1 < attempts:
            time.sleep(0.15 * (attempt + 1))

    log(f"serial send failed on {port}: {last_error}", error=True)
    return False


def send_state(state: str) -> bool:
    if state not in VALID_STATES:
        log(f"invalid state: {state}", error=True)
        return False
    if env_bool("STATUS_LIGHT_SIMULATE"):
        log(f"simulate send: {state}")
        return True
    if serial is None:
        log(
            "pyserial is not installed. Run: "
            "python -m pip install -r codex_hooks/requirements.txt",
            error=True,
        )
        return False

    try:
        baud = int(os.getenv("STATUS_LIGHT_BAUD", str(DEFAULT_BAUD)))
    except ValueError:
        baud = DEFAULT_BAUD

    try:
        with serial_lock():
            if was_recently_sent(state):
                log(f"debounced state: {state}")
                return True
            port = find_serial_port()
            if not port:
                log(
                    "no supported USB serial port found. Run --list-ports or set "
                    "STATUS_LIGHT_PORT, for example: setx STATUS_LIGHT_PORT COM7",
                    error=True,
                )
                return False
            if not _write_state_with_ack(port, baud, state):
                return False
            record_send(state)
            log(f"sent {state} to {port}")
            return True
    except (OSError, TimeoutError) as exc:
        log(f"serial lock failed: {exc}", error=True)
        return False


def handle_payload(payload: dict[str, Any]) -> int:
    event = find_hook_event(payload)
    if not event:
        log("ignored payload without hook_event_name")
        return 0

    state = choose_state(event, payload, load_mapping())
    if not state:
        log(f"ignored event: {event}")
    else:
        # Hardware failure must not block Codex itself.
        send_state(state)

    # Codex requires JSON stdout for these two stop events when exit code is 0.
    if event in {"SubagentStop", "Stop"}:
        print("{}")
    return 0


def print_serial_ports() -> int:
    if serial is None:
        print("pyserial is not installed", file=sys.stderr)
        return 1
    ports = available_serial_ports()
    if not ports:
        print("No serial ports detected.")
        return 1
    for port in ports:
        vid = getattr(port, "vid", None)
        pid = getattr(port, "pid", None)
        identity = f"VID:PID={vid:04X}:{pid:04X}" if vid is not None and pid is not None else "VID:PID=unknown"
        print(f"{port.device}\t{port.description}\t{identity}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send Codex hook status to a serial traffic light."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--state", choices=sorted(VALID_STATES))
    group.add_argument("--event", help="Simulate a Codex hook event name.")
    group.add_argument("--list-ports", action="store_true")
    parser.add_argument(
        "--simulate", action="store_true", help="Log instead of opening serial."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.simulate:
        os.environ["STATUS_LIGHT_SIMULATE"] = "1"
    if args.list_ports:
        return print_serial_ports()
    if args.state:
        return 0 if send_state(args.state) else 1
    if args.event:
        return handle_payload({"hook_event_name": args.event})

    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        log(f"invalid hook JSON: {exc}", error=True)
        return 0
    if not isinstance(payload, dict):
        log("ignored non-object hook payload")
        return 0
    return handle_payload(payload)


if __name__ == "__main__":
    raise SystemExit(main())
