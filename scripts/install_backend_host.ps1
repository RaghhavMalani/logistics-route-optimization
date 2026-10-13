param(
    [string]$PythonExe = 'C:\Users\Raghh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe',
    [string]$StateDir,
    [int]$Port = 8000,
    [string]$Account,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $StateDir) { $StateDir = Join-Path $repoRoot 'outputs' }
$resolvedState = (Resolve-Path -LiteralPath $StateDir).Path
$resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
$hostFolder = Join-Path $resolvedState 'backend_service'
New-Item -ItemType Directory -Path $hostFolder -Force | Out-Null
$deps = Join-Path $repoRoot '.portwatch/backend-runtime'
if (-not (Test-Path -LiteralPath (Join-Path $deps 'fastapi'))) {
    New-Item -ItemType Directory -Path $deps -Force | Out-Null
    # Copy verified library overrides only; this contains no QA records.
    Copy-Item -Path (Join-Path $repoRoot 'work/test-runtime/*') -Destination $deps -Recurse -Force
}
$site = Join-Path $repoRoot '.venv/Lib/site-packages'
$entry = Join-Path $repoRoot 'scripts/run_backend_host.py'
$arguments = '"{0}" --state-dir "{1}" --dependency-dir "{2}" --dependency-dir "{3}" --port {4}' -f $entry,$resolvedState,$deps,$site,$Port
$action = New-ScheduledTaskAction -Execute $resolvedPython -Argument $arguments -WorkingDirectory $repoRoot
if (-not $Account) { $Account = [Security.Principal.WindowsIdentity]::GetCurrent().Name }
$principal = New-ScheduledTaskPrincipal -UserId $Account -LogonType S4U -RunLevel Limited
$startup = New-ScheduledTaskTrigger -AtStartup
$recovery = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$task = New-ScheduledTask -Action $action -Trigger @($startup,$recovery) -Principal $principal -Settings $settings -Description "PortWatch persistent backend. One scheduler, existing durable state, official PDF collectors; VesselFinder disabled."
$taskName = 'PortWatch Backend'
$xml = Export-ScheduledTask -InputObject $task
$xml | Set-Content -LiteralPath (Join-Path $hostFolder 'windows-task.xml') -Encoding Unicode
if ($PrepareOnly) { Write-Output "Prepared task definition in $hostFolder"; exit 0 }
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and (($existing.Actions.Execute -ne $resolvedPython) -or ($existing.Actions.Arguments -ne $arguments))) {
    throw 'An existing PortWatch Backend task has different configuration; it was not replaced.'
}
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force -ErrorAction Stop | Out-Null
Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
Write-Output "Registered and started '$taskName' as $Account (S4U, task runs without elevation)."
