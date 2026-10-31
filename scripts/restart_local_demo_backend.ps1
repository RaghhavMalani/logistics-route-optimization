# Dedicated local QA only. No hosting, credentials or production-volume access.
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskRun=Join-Path $taskRoot 'work/current-source-demo/run_backend.ps1'
if (-not (Test-Path -LiteralPath $taskRun)) { throw 'Prepare the documented isolated local backend first.' }
$taskSocket=Get-NetTCPConnection -LocalPort 8817 -State Listen -ErrorAction SilentlyContinue
if ($taskSocket) {
  $taskProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$($taskSocket.OwningProcess)"
  if ($taskProcess.CommandLine -notmatch 'uvicorn backend.app.main:app --host 127.0.0.1 --port 8817') {throw 'Port 8817 is not the designated QA backend.'}
  Stop-Process -Id $taskProcess.ProcessId -ErrorAction Stop
}
$taskShell=(Get-Process -Id $PID).Path
Start-Process -FilePath $taskShell -ArgumentList @('-NoProfile','-File',$taskRun) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRoot 'work/current-source-demo/restarted.stdout.log') -RedirectStandardError (Join-Path $taskRoot 'work/current-source-demo/restarted.stderr.log') | Out-Null
Write-Output 'Dedicated local backend restarted; durable QA state retained.'
