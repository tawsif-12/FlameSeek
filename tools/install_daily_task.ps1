param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [string]$At = '08:00',
    [string]$TaskName = 'FlameSeek-Daily-FIRMS'
)
$ErrorActionPreference = 'Stop'
$pythonExe = (Resolve-Path -LiteralPath $PythonPath).Path
$runner = Join-Path $PSScriptRoot 'run_daily.ps1'
# Windows uses the computer's LOCAL timezone. Configure the host timezone as desired.
$arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -PythonPath "{1}"' -f $runner,$pythonExe
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 30) -ExecutionTimeLimit (New-TimeSpan -Hours 20)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Download FIRMS observations and publish validated FlameSeek fire history daily.' -Force
