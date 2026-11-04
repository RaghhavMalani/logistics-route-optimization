$ErrorActionPreference = 'Stop'
$run = Join-Path $PSScriptRoot 'work/panel/run'

foreach ($name in 'terminal', 'api') {
    $receipt = Join-Path $run "$name.json"
    if (!(Test-Path -LiteralPath $receipt)) { continue }
    $identity = Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
    $process = Get-Process -Id $identity.id -ErrorAction SilentlyContinue
    if ($process -and [string]$process.StartTime.ToUniversalTime().Ticks -eq $identity.started) {
        # The Windows Python virtualenv launcher can own a child Python process.
        $null = & taskkill.exe /PID $process.Id /T /F 2>&1
        if ($LASTEXITCODE -and (Get-Process -Id $identity.id -ErrorAction SilentlyContinue)) {
            throw "Could not stop the panel $name process ($($process.Id))."
        }
        $null = $process.WaitForExit(5000)
    }
    Remove-Item -LiteralPath $receipt
}
