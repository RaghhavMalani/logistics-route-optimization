param(
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$ExpectedSha,
    [Parameter(Mandatory)][string]$Package,
    [Parameter(Mandatory)][string]$EvidenceDir
)
$ErrorActionPreference = 'Stop'
$evidence = (Resolve-Path -LiteralPath $EvidenceDir).Path
$packageRoot = (Resolve-Path -LiteralPath $Package).Path
$manifest = Get-Content -LiteralPath (Join-Path $packageRoot 'data/preview_release/source-manifest.json') -Raw | ConvertFrom-Json
$backup = Get-Content -LiteralPath (Join-Path $evidence 'backup.json') -Raw | ConvertFrom-Json
$cleanup = Get-Content -LiteralPath (Join-Path $evidence 'backup-key-removed.json') -Raw | ConvertFrom-Json
if ($manifest.applicationSha -ne $ExpectedSha -or $backup.releaseSha -ne $ExpectedSha -or -not $cleanup.removed -or -not $backup.signature) {
    throw 'Package, verified backup, or temporary key cleanup is missing'
}
if (-not (Test-Path -LiteralPath (Join-Path $evidence 'ROLLBACK.md'))) { throw 'Record both rollback targets before deploying' }
$vercel = vercel api '/v9/projects/prj_7rUm8f8iofYg1cSMlrROZsK7iWP0' --scope flash2404s-projects | ConvertFrom-Json
if ($LASTEXITCODE -or $vercel.autoAssignCustomDomains -ne $false) { throw 'Hold automatic Vercel production assignment before deploying' }
& (Join-Path $PSScriptRoot 'Invoke-ProductionVolume.ps1') -Action deploy-check -ExpectedSha $ExpectedSha `
    -Name $backup.name -Signature $backup.signature -EvidenceDir $evidence

$target = @('--project','983b8896-688f-47ea-a693-6985e84ab03b','--environment','7a940de4-9c13-411e-ad59-eb30ee42a9d4','--service','128a61e8-a333-4c93-aa77-550d4e923495')
# Keep mutable provider inputs outside the reviewed image so a restart can still
# verify all of its original bytes.
railway variable set "PORTWATCH_RELEASE_SHA=$ExpectedSha" 'PORTWATCH_RELEASE_ENVIRONMENT=production' `
    'PORTWATCH_REQUIRE_RELEASE_MANIFEST=1' 'PORTWATCH_PUBLIC_EVIDENCE_SEED_MANIFEST=/app/data/cache/preview_public_seed/manifest.json' `
    'PORTWATCH_DATA_DIR=/app/state/live/data' 'PORTWATCH_CACHE_DIR=/app/state/live/data/cache' 'PORTWATCH_OUTPUTS_DIR=/app/state/live/outputs' `
    'PORTWATCH_SOURCE_SNAPSHOT_URL=sqlite:////app/state/live/source-snapshots.sqlite3' `
    'PORTWATCH_PUBLISH_REVIEWED_SOURCES=open-meteo-marine-extended,open-meteo-ensemble,frankfurter-ecb-fx' `
    'PORTWATCH_REFRESH_CONCURRENCY=4' 'PORTWATCH_REFRESH_TICK_SECONDS=5' @target --skip-deploys --json | Out-Null
if ($LASTEXITCODE) { throw 'Railway production release settings update failed' }
Push-Location -LiteralPath $packageRoot
try {
    railway up . @target --path-as-root --no-gitignore --detach --json | Tee-Object (Join-Path $evidence 'production-railway-upload.json')
    if ($LASTEXITCODE) { throw 'Railway production upload failed' }
} finally { Pop-Location }
