param(
  [switch]$InstallPythonDeps,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$ToolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ToolDir
$HookScript = Join-Path $Root "codex_hooks\send_signal.py"
$Requirements = Join-Path $Root "codex_hooks\requirements.txt"

if (-not (Test-Path $HookScript)) {
  throw "Cannot find hook script: $HookScript"
}

if ($InstallPythonDeps) {
  python -m pip install -r $Requirements
}

$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
New-Item -ItemType Directory -Force -Path $CodexHome | Out-Null

$HooksPath = Join-Path $CodexHome "hooks.json"
if ((Test-Path $HooksPath) -and -not $Force) {
  $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $BackupPath = "$HooksPath.bak-$Stamp"
  Copy-Item $HooksPath $BackupPath
  Write-Host "Existing hooks.json backed up to $BackupPath"
}

$CommandWindows = "python `"$HookScript`""
$CommandPosix = "python3 `"$($HookScript -replace '\\', '/')`""

function New-Hook($message) {
  return @(
    [ordered]@{
      type = "command"
      command = $CommandPosix
      commandWindows = $CommandWindows
      timeout = 5
      statusMessage = $message
    }
  )
}

$Config = [ordered]@{
  hooks = [ordered]@{
    SessionStart = @(
      [ordered]@{
        matcher = "startup|resume|clear|compact"
        hooks = New-Hook "Status light: session start"
      }
    )
    UserPromptSubmit = @(
      [ordered]@{
        hooks = New-Hook "Status light: thinking"
      }
    )
    PreToolUse = @(
      [ordered]@{
        matcher = "Bash|apply_patch|Edit|Write|mcp__.*"
        hooks = New-Hook "Status light: tool running"
      }
    )
    PermissionRequest = @(
      [ordered]@{
        hooks = New-Hook "Status light: waiting for approval"
      }
    )
    PostToolUse = @(
      [ordered]@{
        matcher = "Bash|apply_patch|Edit|Write|mcp__.*"
        hooks = New-Hook "Status light: tool finished"
      }
    )
    SubagentStop = @(
      [ordered]@{
        hooks = New-Hook "Status light: subagent stopped"
      }
    )
    Stop = @(
      [ordered]@{
        hooks = New-Hook "Status light: turn complete"
      }
    )
  }
}

$Json = $Config | ConvertTo-Json -Depth 12
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($HooksPath, $Json + [Environment]::NewLine, $Utf8NoBom)

Write-Host "Codex hooks written to $HooksPath"
Write-Host "Next: restart Codex or start a new Codex CLI session, then run /hooks and trust the new hook."
Write-Host "If the wrong COM port is selected, run: setx STATUS_LIGHT_PORT COM5"
