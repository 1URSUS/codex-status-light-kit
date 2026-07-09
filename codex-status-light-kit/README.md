# Codex Status Light Kit

这是一个以 `leenc123/claude-traffic-light-control` 为蓝本重写的 Codex 状态灯小项目。

它把 Codex 本地客户端或 Codex CLI 的生命周期事件映射到一个实体三色状态灯：

| 灯效 | 状态 | 含义 |
| --- | --- | --- |
| 绿灯闪烁 | `IDLE` | 空闲，等你发任务 |
| 黄灯闪烁 | `THINKING` | Codex 正在思考或调用工具 |
| 红灯常亮 | `WAITING_USER` | Codex 正在等你批准命令或操作 |
| 绿灯常亮 | `TASK_COMPLETE` | 当前回合完成，60 秒后回到空闲 |
| 红灯闪烁 | `TOOL_ERROR` | 检测到工具调用失败 |

## 包内容

```text
codex-status-light-kit/
  codex_hooks/
    send_signal.py              # Codex hook: 读取事件并发送串口状态
    hook_mapping.json           # 事件到灯效的映射
    hooks.codex.example.json    # Codex hooks.json 模板
    requirements.txt            # Python 依赖
  debug_tools/
    test_serial_command.py      # 手动发送状态到灯
    simulate_hook_event.py      # 模拟 Codex hook 事件
  firmware/
    traffic_light_controller/
      traffic_light_controller.ino
      pins_config.h
  tools/
    install_windows.ps1         # Windows 一键生成 ~/.codex/hooks.json
  小白指南.md
```

## 最快路线

1. 按 `小白指南.md` 里的接线表接好红、黄、绿三颗 LED。
2. 用 Arduino IDE 烧录 `firmware/traffic_light_controller/traffic_light_controller.ino`。
3. 安装 Python 依赖：

```powershell
python -m pip install -r .\codex_hooks\requirements.txt
```

4. 先手动测试：

```powershell
python .\debug_tools\test_serial_command.py THINKING
python .\debug_tools\test_serial_command.py WAITING_USER
python .\debug_tools\test_serial_command.py TASK_COMPLETE
```

5. 生成 Codex hook 配置：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\install_windows.ps1
```

6. 重启 Codex 或开启新线程，在 CLI 里用 `/hooks` 审查并信任这个 hook。

详细步骤见 [小白指南.md](./小白指南.md)。

## 来源说明

硬件状态设计和灯效语义参考了 `leenc123/claude-traffic-light-control` 的公开 README；本包中的 Codex 适配层、配置模板、安装脚本和指南为重新整理后的实现，重点面向 Codex 本地客户端和 CLI。
