$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$terminal = Join-Path $root 'india-portwatch-terminal'
$run = Join-Path $root 'work/panel/run'
$apiPort = 9299
$terminalPort = 4264
$api = "http://127.0.0.1:$apiPort/api"
$origin = "http://127.0.0.1:$terminalPort"
$login = "$origin/login"

$sha = git -C $root rev-parse HEAD
if ($LASTEXITCODE) { throw 'Could not read the panel checkout SHA.' }
git -C $root -c core.safecrlf=false diff --quiet HEAD --
if ($LASTEXITCODE) { throw 'The panel checkout has tracked changes. Start from a committed build.' }

$python = (Get-Command python.exe).Source
& $python -c 'import fastapi, uvicorn, pandas, numpy'
if ($LASTEXITCODE) { throw 'Activate the Python environment with the backend dependencies and try again.' }
$node = (Get-Command node.exe).Source
$vite = Join-Path $terminal 'node_modules/vite/bin/vite.js'
if (!(Test-Path -LiteralPath $vite)) { throw 'Install the terminal dependencies before starting the panel.' }
$snapshot = Get-Content -LiteralPath (Join-Path $root 'data/cache/provenance.json') -Raw | ConvertFrom-Json
$at = [DateTimeOffset]::Parse($snapshot.forecastOrigin, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal)

New-Item -ItemType Directory -Force -Path $run | Out-Null
& (Join-Path $root 'stop-panel.ps1')
# Migrate the older panel launcher only when its listeners identify this checkout.
$legacyApi = Get-NetTCPConnection -State Listen -LocalPort $apiPort -ErrorAction SilentlyContinue
if ($legacyApi) {
    try { $legacyHealth = Invoke-RestMethod -Uri "$api/health" -TimeoutSec 3 } catch { $legacyHealth = $null }
    if ($legacyHealth.durableStores.stateDir -eq (Join-Path $root '.portwatch\panel-state')) {
        $legacyTerminal = Get-NetTCPConnection -State Listen -LocalPort $terminalPort -ErrorAction SilentlyContinue
        if ($legacyTerminal) {
            $legacyProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($legacyTerminal.OwningProcess)"
            if ($legacyProcess.CommandLine -like "*$(Join-Path $terminal '.output\server\index.mjs')*") {
                Stop-Process -Id $legacyTerminal.OwningProcess
            }
        }
        Stop-Process -Id $legacyApi.OwningProcess
    }
}
foreach ($port in $apiPort, $terminalPort) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port belongs to another process. Stop that process before starting the panel."
    }
}

$settings = @{
    PORTWATCH_RELEASE_SHA = $sha
    PORTWATCH_LICENCE_MODE = 'DEMO'
    PORTWATCH_IDENTITY_MODE = 'verified'
    PORTWATCH_PANEL_SNAPSHOT_AT = $at.ToString('o')
    PORTWATCH_FRESHNESS_SCHEDULER = '0'
    PORTWATCH_STATE_DIR = Join-Path $run 'state'
    VITE_PORTWATCH_API_BASE = $api
    NITRO_PRESET = 'node-server'
    HOST = '127.0.0.1'
    PORT = [string]$terminalPort
}
$original = @{}

function Start-PanelService($name, $executable, $arguments, $directory) {
    $process = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $directory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $run "$name.log") -RedirectStandardError (Join-Path $run "$name.err.log")
    $identity = @{ id = $process.Id; started = [string]$process.StartTime.ToUniversalTime().Ticks }
    $identity | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $run "$name.json")
    return $process
}

try {
    foreach ($key in $settings.Keys) {
        $original[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process')
    }

    $releasePath = Join-Path $terminal 'public/release.json'
    $releaseJson = @{ applicationSha = $sha; scope = 'LOCAL_PANEL' } | ConvertTo-Json
    New-Item -ItemType File -Path $releasePath -Value $releaseJson | Out-Null
    try {
        $build = Start-Process -FilePath $node -ArgumentList 'node_modules/vite/bin/vite.js build' -WorkingDirectory $terminal -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $run 'build.log') -RedirectStandardError (Join-Path $run 'build.err.log')
    } finally {
        Remove-Item -LiteralPath $releasePath
    }
    if ($build.ExitCode -ne 0) { throw "Terminal build failed. See $run\build.err.log." }
    if ((git -C $root rev-parse HEAD) -ne $sha) { throw 'The checkout changed during the panel build.' }
    git -C $root -c core.safecrlf=false diff --quiet HEAD --
    if ($LASTEXITCODE) { throw 'The panel sources changed during the build.' }
    $backend = Start-PanelService 'api' $python "-m src.portwatch_os.panel_runtime backend.app.main:app --host 127.0.0.1 --port $apiPort" $root
    $frontend = Start-PanelService 'terminal' $node '.output/server/index.mjs' $terminal

    $deadline = (Get-Date).AddMinutes(2)
    do {
        if ($backend.HasExited -or $frontend.HasExited) { throw "A panel process exited. See the logs in $run." }
        try {
            $health = Invoke-RestMethod -Uri "$api/health" -TimeoutSec 3
            $release = Invoke-RestMethod -Uri "$origin/release.json" -TimeoutSec 3
            $page = Invoke-WebRequest -Uri $login -UseBasicParsing -TimeoutSec 3
            if ($health.status -eq 'ok' -and $health.release.sha -eq $sha -and
                $release.applicationSha -eq $sha -and $page.StatusCode -eq 200) {
                $dot = [char]0x00B7
                Write-Output "READY $dot open $login $dot SHA $sha"
                return
            }
        } catch {
            # The listeners may still be starting.
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Panel readiness timed out. See the logs in $run."
} catch {
    & (Join-Path $root 'stop-panel.ps1')
    throw
} finally {
    foreach ($key in $original.Keys) {
        [Environment]::SetEnvironmentVariable($key, $original[$key], 'Process')
    }
}
