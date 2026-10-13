param(
    [ValidateSet('Status','Restart','Stop','Start')][string]$Action = 'Status',
    [string]$StateDir
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $StateDir) { $StateDir = Join-Path $repoRoot 'outputs' }
$resolvedState = (Resolve-Path -LiteralPath $StateDir).Path
$folder = Join-Path $resolvedState 'backend_service'
$taskName = 'PortWatch Backend'
if ($Action -eq 'Status') {
    Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
    Get-ScheduledTaskInfo -TaskName $taskName | Select-Object LastRunTime,LastTaskResult,NextRunTime
    if (Test-Path -LiteralPath (Join-Path $folder 'host-status.json')) {
        Get-Content -LiteralPath (Join-Path $folder 'host-status.json')
    }
    exit 0
}
if ($Action -in @('Stop','Restart')) {
    $administrator = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $administrator) { throw 'Windows requires an Administrator PowerShell session to disable this installed task during a controlled stop/restart.' }
    # Disable recovery while carrying out an intentional graceful stop.
    Disable-ScheduledTask -TaskName $taskName -ErrorAction Stop | Out-Null
    $status = Get-Content -LiteralPath (Join-Path $folder 'host-status.json') -Raw | ConvertFrom-Json
    @{runId=$status.runId;action='stop';requestedAt=[DateTimeOffset]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $folder 'control.json') -Encoding UTF8
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        $current = Get-Content -LiteralPath (Join-Path $folder 'host-status.json') -Raw | ConvertFrom-Json
        if ($current.stopped) { break }
        Start-Sleep -Seconds 1
    }
    if (-not $current.stopped) { throw 'Graceful stop timed out. Recovery remains disabled; inspect backend.log before intervening.' }
    # Wait briefly for the task action to exit after writing its final status.
    Start-Sleep -Seconds 2
}
if ($Action -in @('Start','Restart')) {
    Enable-ScheduledTask -TaskName $taskName -ErrorAction Stop | Out-Null
    Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
}
Write-Output "Backend host action: $Action"
