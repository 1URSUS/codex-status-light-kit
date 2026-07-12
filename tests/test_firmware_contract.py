from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIRMWARE = ROOT / "firmware" / "traffic_light_controller"


class FirmwareContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sketch = (FIRMWARE / "traffic_light_controller.ino").read_text(
            encoding="utf-8"
        )
        cls.pins = (FIRMWARE / "pins_config.h").read_text(encoding="utf-8")

    def test_has_no_external_json_or_eeprom_dependency(self) -> None:
        self.assertNotIn("ArduinoJson", self.sketch)
        self.assertNotIn("EEPROM", self.sketch)

    def test_serial_protocol_matches_python_client(self) -> None:
        self.assertIn("const unsigned long SERIAL_BAUD = 115200", self.sketch)
        self.assertIn('Serial.print("State: ")', self.sketch)
        self.assertIn('input.indexOf("\\\"state\\\"")', self.sketch)

    def test_default_nodemcu_pins_are_stable(self) -> None:
        self.assertIn("#define PIN_RED D1", self.pins)
        self.assertIn("#define PIN_YELLOW D2", self.pins)
        self.assertIn("#define PIN_GREEN D7", self.pins)
        self.assertIn("#define LED_ACTIVE_LOW 0", self.pins)

    def test_waiting_state_does_not_expire(self) -> None:
        self.assertNotIn("WAITING_IDLE_AFTER", self.sketch)


if __name__ == "__main__":
    unittest.main()
