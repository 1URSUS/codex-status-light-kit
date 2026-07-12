# Codex Status Light Kit

一个面向 Codex 桌面客户端和 Codex CLI 的 ESP8266 实体三色状态灯。它通过 Codex 生命周期 hooks 接收本机事件，再通过 USB 串口控制 NodeMCU/ESP-12F 开发板上的红、黄、绿 LED。

| 灯效 | 状态 | 含义 |
| --- | --- | --- |
| 绿灯闪烁 | `IDLE` | 空闲，等待新任务 |
| 黄灯闪烁 | `THINKING` | Codex 正在思考或调用工具 |
| 红灯常亮 | `WAITING_USER` | Codex 正在等待批准或输入 |
| 绿灯常亮 | `TASK_COMPLETE` | 当前回合完成，60 秒后回到空闲 |
| 红灯闪烁 | `TOOL_ERROR` | 检测到工具调用失败 |

## 适用范围

- Windows 10/11
- Codex 桌面客户端的本地任务，或 Codex CLI
- Python 3.10 及以上版本
- NodeMCU ESP8266 开发板，ESP-12E/ESP-12F 均可
- CH340/CH341/CH343、CH910x 或 CP210x USB 转串口芯片

本项目依赖电脑本地 USB 串口，因此不适用于纯 Codex Cloud 任务。WSL 用户需要先把串口映射进 WSL；Windows 初学者建议直接在 Windows PowerShell 中运行。

## 快速开始

完整接线、烧录、驱动和故障排查请看 [小白指南](./小白指南.md)。最短流程如下：

1. 按指南把红、黄、绿 LED 接到 `D1`、`D2`、`D7`，每颗 LED 串联一个 220 欧姆电阻。
2. 用 Arduino IDE 烧录 `firmware/traffic_light_controller/traffic_light_controller.ino`。
3. 安装 Python 依赖：

   ```powershell
   python -m pip install -r .\codex_hooks\requirements.txt
   ```

4. 查看串口并手动测试：

   ```powershell
   python .\codex_hooks\send_signal.py --list-ports
   python .\debug_tools\test_serial_command.py THINKING
   python .\debug_tools\test_serial_command.py TASK_COMPLETE
   ```

5. 安装 Codex hooks：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\tools\install_windows.ps1 -InstallPythonDeps
   ```

6. 重启 Codex 或开启新任务。在 Codex CLI 中运行 `/hooks`，审查并信任状态灯 hook。

安装脚本会保留已有 hooks，只替换本项目以前安装的状态灯条目，并在改写前备份原来的 `%USERPROFILE%\.codex\hooks.json`。

## 目录结构

```text
codex-status-light-kit/
  codex_hooks/
    send_signal.py
    hook_mapping.json
    hooks.codex.example.json
    requirements.txt
  debug_tools/
    test_serial_command.py
    simulate_hook_event.py
  firmware/traffic_light_controller/
    traffic_light_controller.ino
    pins_config.h
  tools/
    install_windows.ps1
  tests/
  小白指南.md
```

## 常用设置

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `STATUS_LIGHT_PORT` | 自动识别 | 固定串口，例如 `COM7` |
| `STATUS_LIGHT_BAUD` | `115200` | 固件串口波特率 |
| `STATUS_LIGHT_SIMULATE` | `0` | 设为 `1` 时只写日志，不操作硬件 |
| `STATUS_LIGHT_LOG_DIR` | `%LOCALAPPDATA%\codex-status-light-kit\logs` | 日志和进程锁目录 |
| `STATUS_LIGHT_DEBOUNCE_SECONDS` | `0.6` | 合并短时间内重复状态 |
| `STATUS_LIGHT_SERIAL_RETRIES` | `3` | 串口发送重试次数 |

更改 `codex_hooks/hook_mapping.json` 可以自定义 Codex 事件与灯效的对应关系。

## 开发与验证

```powershell
python -m unittest discover -s tests -v
powershell -ExecutionPolicy Bypass -File .\tests\test_install_windows.ps1
```

Codex hooks 的事件和配置格式以 [OpenAI Codex Hooks 文档](https://developers.openai.com/codex/hooks)为准。

## 来源与许可证

本项目的硬件状态灯构想和灯效语义受到 [leenc123/claude-traffic-light-control](https://github.com/leenc123/claude-traffic-light-control) 启发；Codex 适配层、串口协议、安装脚本、固件和文档为面向 Codex 的重新实现。

项目采用 [MIT License](./LICENSE)。Codex 是 OpenAI 的产品；本项目是独立社区项目，不代表 OpenAI 官方。
