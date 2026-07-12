from __future__ import annotations

import json
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "codex_hooks"))

import send_signal  # noqa: E402


class SendSignalTests(unittest.TestCase):
    ENV_KEYS = (
        "STATUS_LIGHT_PORT",
        "STATUS_LIGHT_LOG_DIR",
        "STATUS_LIGHT_SIMULATE",
        "STATUS_LIGHT_DEBOUNCE_SECONDS",
    )

    def setUp(self) -> None:
        self.previous_env = {key: os.environ.get(key) for key in self.ENV_KEYS}
        for key in self.ENV_KEYS:
            os.environ.pop(key, None)
        self.temporary_directory = tempfile.TemporaryDirectory()
        os.environ["STATUS_LIGHT_LOG_DIR"] = self.temporary_directory.name

    def tearDown(self) -> None:
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temporary_directory.cleanup()

    def test_reads_documented_hook_event_name(self) -> None:
        payload = {"hook_event_name": "UserPromptSubmit"}
        self.assertEqual(send_signal.find_hook_event(payload), "UserPromptSubmit")

    def test_detects_failed_tool_response(self) -> None:
        payload = {
            "tool_input": {"error": "this is only input text"},
            "tool_response": {"metadata": {"exit_code": 1}},
        }
        self.assertTrue(send_signal.post_tool_use_failed(payload))

    def test_does_not_treat_tool_input_as_failure(self) -> None:
        payload = {
            "tool_input": {"error": "this is only input text"},
            "tool_response": {"metadata": {"exit_code": 0}},
        }
        self.assertFalse(send_signal.post_tool_use_failed(payload))

    def test_failed_post_tool_use_maps_to_error_state(self) -> None:
        mapping = send_signal.load_mapping()
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_response": {"success": False},
        }
        self.assertEqual(
            send_signal.choose_state("PostToolUse", payload, mapping), "TOOL_ERROR"
        )

    def test_prefers_wch_usb_serial_and_ignores_bluetooth(self) -> None:
        bluetooth = SimpleNamespace(
            device="COM4",
            description="Standard Serial over Bluetooth link",
            manufacturer="Microsoft",
            hwid="BTHENUM",
            vid=None,
            pid=None,
        )
        ch343 = SimpleNamespace(
            device="COM7",
            description="USB-Enhanced-SERIAL CH343",
            manufacturer="wch.cn",
            hwid="USB VID:PID=1A86:55D3",
            vid=0x1A86,
            pid=0x55D3,
        )
        self.assertEqual(send_signal.find_serial_port([bluetooth, ch343]), "COM7")

    def test_never_falls_back_to_bluetooth_port(self) -> None:
        bluetooth = SimpleNamespace(
            device="COM4",
            description="Standard Serial over Bluetooth link",
            manufacturer="Microsoft",
            hwid="BTHENUM",
            vid=None,
            pid=None,
        )
        self.assertIsNone(send_signal.find_serial_port([bluetooth]))

    def test_forced_port_takes_precedence(self) -> None:
        os.environ["STATUS_LIGHT_PORT"] = "COM9"
        self.assertEqual(send_signal.find_serial_port([]), "COM9")

    def test_simulation_writes_log_without_serial(self) -> None:
        os.environ["STATUS_LIGHT_SIMULATE"] = "1"
        self.assertTrue(send_signal.send_state("THINKING"))
        log_text = (Path(self.temporary_directory.name) / "status_light.log").read_text(
            encoding="utf-8"
        )
        self.assertIn("simulate send: THINKING", log_text)

    def test_recent_success_is_debounced(self) -> None:
        send_signal.record_send("THINKING")
        self.assertTrue(send_signal.was_recently_sent("THINKING"))
        self.assertFalse(send_signal.was_recently_sent("TASK_COMPLETE"))

    def test_mapping_file_is_valid(self) -> None:
        data = json.loads(
            (ROOT / "codex_hooks" / "hook_mapping.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["Stop"], "TASK_COMPLETE")

    def test_stop_events_emit_required_json_stdout(self) -> None:
        os.environ["STATUS_LIGHT_SIMULATE"] = "1"
        output = io.StringIO()
        with redirect_stdout(output):
            result = send_signal.handle_payload({"hook_event_name": "Stop"})
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue().strip(), "{}")

    def test_non_stop_events_remain_quiet_on_stdout(self) -> None:
        os.environ["STATUS_LIGHT_SIMULATE"] = "1"
        output = io.StringIO()
        with redirect_stdout(output):
            result = send_signal.handle_payload(
                {"hook_event_name": "UserPromptSubmit"}
            )
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
