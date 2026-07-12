# Contributing

Issues and pull requests are welcome. Please keep changes focused and avoid committing generated files, logs, local paths, or hardware-specific COM port numbers.

## Local checks

```powershell
python -m pip install -r .\codex_hooks\requirements.txt
python -m unittest discover -s tests -v
powershell -ExecutionPolicy Bypass -File .\tests\test_install_windows.ps1
```

Firmware changes should also be verified with Arduino IDE or Arduino CLI using the `NodeMCU 1.0 (ESP-12E Module)` board profile.
