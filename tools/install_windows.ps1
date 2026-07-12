param(
  [switch]$InstallPythonDeps,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$ToolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ToolDir
$HookScript = Join-Path $Root "codex_hooks\send_signal.py"
$Requirements = Join-Path $Root "codex_hooks\requirements.txt"

if (-not (Test-Path -LiteralPath $HookScript)) {
  throw "Cannot find hook script: $HookScript"
}

function Resolve-PythonCommand {
  $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
  if ($PyLauncher) {
    & $PyLauncher.Source -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
      return [pscustomobject]@{
        Executable = $PyLauncher.Source
        Arguments = @("-3")
      }
    }
  }

  $Python = Get-Command python -ErrorAction SilentlyContinue
  if ($Python) {
    & $Python.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
      return [pscustomobject]@{
        Executable = $Python.Source
        Arguments = @()
      }
    }
  }

  throw "Python 3 was not found. Install Python 3, reopen PowerShell, and run this script again."
}

$PythonCommand = Resolve-PythonCommand
if ($InstallPythonDeps) {
  & $PythonCommand.Executable @($PythonCommand.Arguments) -m pip install -r $Requirements
  if ($LASTEXITCODE -ne 0) {
    throw "Installing Python dependencies failed with exit code $LASTEXITCODE."
  }
}

$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
New-Item -ItemType Directory -Force -Path $CodexHome | Out-Null

$HooksPath = Join-Path $CodexHome "hooks.json"
$BackupPath = $null
if (Test-Path -LiteralPath $HooksPath) {
  $Stamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
  $BackupPath = "$HooksPath.bak-$Stamp"
  Copy-Item -LiteralPath $HooksPath -Destination $BackupPath
}

$QuotedPython = '"' + $PythonCommand.Executable + '"'
$PythonArguments = $PythonCommand.Arguments -join " "
$CommandWindows = (($QuotedPython, $PythonArguments, ('"' + $HookScript + '"')) -join " ").Trim()
$CommandPosix = "python3 `"$($HookScript -replace '\\', '/')`""

function New-CommandHook([string]$Message) {
  return [pscustomobject][ordered]@{
    type = "command"
    command = $CommandPosix
    commandWindows = $CommandWindows
    timeout = 12
    statusMessage = $Message
  }
}

function New-HookGroup([string]$Matcher, [string]$Message) {
  $Group = [ordered]@{}
  if ($Matcher) {
    $Group.matcher = $Matcher
  }
  $Group.hooks = @((New-CommandHook $Message))
  return [pscustomobject]$Group
}

$StatusLightGroups = [ordered]@{
  SessionStart = New-HookGroup "startup|resume|clear|compact" "Status light: session start"
  UserPromptSubmit = New-HookGroup "" "Status light: thinking"
  PreToolUse = New-HookGroup "Bash|apply_patch|Edit|Write|mcp__.*" "Status light: tool running"
  PermissionRequest = New-HookGroup "" "Status light: waiting for approval"
  PostToolUse = New-HookGroup "Bash|apply_patch|Edit|Write|mcp__.*" "Status light: tool finished"
  SubagentStop = New-HookGroup "" "Status light: subagent stopped"
  Stop = New-HookGroup "" "Status light: turn complete"
}

function Set-ObjectProperty($Object, [string]$Name, $Value) {
  if ($null -eq $Object.PSObject.Properties[$Name]) {
    $Object | Add-Member -MemberType NoteProperty -Name $Name -Value $Value
  } else {
    $Object.$Name = $Value
  }
}

function Test-StatusLightGroup($Group) {
  if ($null -eq $Group) {
    return $false
  }

  foreach ($Handler in @($Group.hooks)) {
    if ($null -eq $Handler) {
      continue
    }
    if ([string]$Handler.statusMessage -like "Status light:*") {
      return $true
    }
    foreach ($Name in @("command", "commandWindows")) {
      $Value = [string]$Handler.$Name
      if ($Value -and $Value.IndexOf("send_signal.py", [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $true
      }
    }
  }
  return $false
}

if (Test-Path -LiteralPath $HooksPath) {
  try {
    $Config = Get-Content -Raw -Encoding UTF8 -LiteralPath $HooksPath | ConvertFrom-Json
  } catch {
    throw "Existing hooks.json is not valid JSON. It was left unchanged. Backup: $BackupPath"
  }
  if ($null -eq $Config -or -not ($Config -is [pscustomobject])) {
    throw "Existing hooks.json must contain a JSON object. It was left unchanged. Backup: $BackupPath"
  }
} else {
  $Config = [pscustomobject]@{}
}

if ($null -eq $Config.PSObject.Properties["hooks"]) {
  $Config | Add-Member -MemberType NoteProperty -Name hooks -Value ([pscustomobject]@{})
} elseif ($null -eq $Config.hooks -or -not ($Config.hooks -is [pscustomobject])) {
  throw "The hooks property in hooks.json must be a JSON object. Existing configuration was left unchanged."
}

foreach ($EventName in $StatusLightGroups.Keys) {
  $ExistingGroups = @()
  $EventProperty = $Config.hooks.PSObject.Properties[$EventName]
  if ($null -ne $EventProperty) {
    $ExistingGroups = @($EventProperty.Value) | Where-Object { -not (Test-StatusLightGroup $_) }
  }
  $MergedGroups = @($ExistingGroups) + @($StatusLightGroups[$EventName])
  Set-ObjectProperty $Config.hooks $EventName $MergedGroups
}

if ($Force) {
  Write-Warning "-Force is retained for compatibility. Existing non-status-light hooks are still preserved."
}

$Json = $Config | ConvertTo-Json -Depth 20
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$TemporaryPath = "$HooksPath.tmp-$PID"
[System.IO.File]::WriteAllText($TemporaryPath, $Json + [Environment]::NewLine, $Utf8NoBom)
Move-Item -LiteralPath $TemporaryPath -Destination $HooksPath -Force

if ($BackupPath) {
  Write-Host "Existing hooks.json backed up to $BackupPath"
}
Write-Host "Codex status-light hooks merged into $HooksPath"
Write-Host "Next: restart Codex or start a new CLI session, then run /hooks and trust the new hook."
Write-Host "To pin the board port, run: setx STATUS_LIGHT_PORT COM7"
