$ErrorActionPreference = "Stop"

function Assert-True([bool]$Condition, [string]$Message) {
  if (-not $Condition) {
    throw $Message
  }
}

$Root = Split-Path -Parent $PSScriptRoot
$Installer = Join-Path $Root "tools\install_windows.ps1"
$TemporaryHome = Join-Path $env:TEMP ("codex-status-light-test-" + [guid]::NewGuid().ToString("N"))
$PreviousCodexHome = $env:CODEX_HOME

try {
  New-Item -ItemType Directory -Path $TemporaryHome | Out-Null
  $Existing = [ordered]@{
    version = 1
    hooks = [ordered]@{
      PreToolUse = @(
        [ordered]@{
          matcher = "^Bash$"
          hooks = @(
            [ordered]@{
              type = "command"
              command = "python custom_hook.py"
              statusMessage = "Custom hook"
            }
          )
        }
      )
    }
  }
  $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  $HooksPath = Join-Path $TemporaryHome "hooks.json"
  [System.IO.File]::WriteAllText(
    $HooksPath,
    ($Existing | ConvertTo-Json -Depth 10),
    $Utf8NoBom
  )

  $env:CODEX_HOME = $TemporaryHome
  & $Installer
  & $Installer

  $Config = Get-Content -Raw -Encoding UTF8 -LiteralPath $HooksPath | ConvertFrom-Json
  Assert-True ($Config.version -eq 1) "Top-level configuration was not preserved."

  $CustomHooks = @(
    @($Config.hooks.PreToolUse) | Where-Object {
      @($_.hooks).statusMessage -contains "Custom hook"
    }
  )
  Assert-True ($CustomHooks.Count -eq 1) "Existing PreToolUse hook was lost or duplicated."

  $Events = @(
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "SubagentStop",
    "Stop"
  )
  foreach ($EventName in $Events) {
    $StatusGroups = @(
      @($Config.hooks.$EventName) | Where-Object {
        $Messages = @($_.hooks) | ForEach-Object { [string]$_.statusMessage }
        @($Messages | Where-Object { $_ -like "Status light:*" }).Count -gt 0
      }
    )
    Assert-True ($StatusGroups.Count -eq 1) "$EventName status-light hook was missing or duplicated."
  }

  $Backups = @(Get-ChildItem -LiteralPath $TemporaryHome -Filter "hooks.json.bak-*")
  Assert-True ($Backups.Count -ge 1) "Existing hooks.json was not backed up."
  Write-Host "Windows installer merge test passed."
} finally {
  if ($null -eq $PreviousCodexHome) {
    Remove-Item Env:CODEX_HOME -ErrorAction SilentlyContinue
  } else {
    $env:CODEX_HOME = $PreviousCodexHome
  }
  if (Test-Path -LiteralPath $TemporaryHome) {
    Remove-Item -LiteralPath $TemporaryHome -Recurse -Force
  }
}
