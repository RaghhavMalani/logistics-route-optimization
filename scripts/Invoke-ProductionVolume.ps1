param(
    [Parameter(Mandatory)][ValidateSet('inventory','prune','backup','deploy-check')][string]$Action,
    [Parameter(Mandatory)][string]$EvidenceDir,
    [string]$Name,
    [string]$Signature,
    [string]$PruneReceipt,
    [string]$ExpectedSha
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$evidence = (Resolve-Path -LiteralPath $EvidenceDir).Path
$argv = @($Action)
if ($Action -eq 'prune') {
    $receipt = Get-Content -LiteralPath $PruneReceipt -Raw | ConvertFrom-Json -AsHashtable
    if (-not $receipt.signatures -or -not (Test-Path -LiteralPath $receipt.history)) {
        throw 'Prune requires recorded backup signatures and rollback history'
    }
    $argv += @('--signatures', ($receipt.signatures | ConvertTo-Json -Compress))
}
if ($Action -in @('backup','deploy-check')) {
    if ($ExpectedSha -notmatch '^[a-f0-9]{40}$' -or $Name -notmatch '^20[0-9]{6}-[a-z0-9-]{3,63}$') {
        throw 'Expected a full release SHA and a dated backup name'
    }
    $gate = Join-Path $evidence "$Action-ci-gate.json"
    python (Join-Path $PSScriptRoot 'verify_release_gate.py') --sha $ExpectedSha --output $gate
    if ($LASTEXITCODE) { throw 'Exact-main CI gate rejected production state operation' }
    $argv += @('--name', $Name)
}
if ($Action -eq 'deploy-check') {
    if ($Signature -notmatch '^[a-f0-9]{64}$') { throw 'The verified backup signature is required' }
    $argv += @('--signature', $Signature)
}

$restore = if ($Action -eq 'backup') { Get-Content -LiteralPath (Join-Path $PSScriptRoot 'restore_production_state.py') -Raw } else { '' }
$payload = @{
    capacity = Get-Content -LiteralPath (Join-Path $root 'src/portwatch_os/state_capacity.py') -Raw
    operator = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'production_volume.py') -Raw
    argv = $argv
    restore = $restore
} | ConvertTo-Json -Depth 5 -Compress
$buffer = [IO.MemoryStream]::new()
$gzip = [IO.Compression.GZipStream]::new($buffer, [IO.Compression.CompressionLevel]::Optimal, $true)
$bytes = [Text.Encoding]::UTF8.GetBytes($payload)
$gzip.Write($bytes, 0, $bytes.Length)
$gzip.Dispose()
$encoded = [Convert]::ToBase64String($buffer.ToArray())
$buffer.Dispose()
$command = @'
python -c 'import base64,gzip,json,sys,types; d=json.loads(gzip.decompress(base64.b64decode("PAYLOAD"))); key="src.portwatch_os.state_capacity"; module=types.ModuleType(key); sys.modules[key]=module; exec(d["capacity"],module.__dict__); operator={}; exec(d["operator"],operator); operator["main"](d["argv"],restore_source=d["restore"])'
'@
$command = $command.Replace('PAYLOAD', $encoded)
$keyName = 'portwatch-volume-' + [Guid]::NewGuid().ToString('N')
$key = Join-Path $evidence $keyName
$registration = "$key.json"
$attempted = $false
$query = 'query {sshPublicKeys(first:100){edges{node{id name fingerprint}}}}'
try {
    ssh-keygen -t ed25519 -N '' -C $keyName -f $key -q
    if ($LASTEXITCODE) { throw 'Temporary key creation failed' }
    @{input=@{name=$keyName; publicKey=(Get-Content -LiteralPath "$key.pub" -Raw).Trim()}} | ConvertTo-Json | Set-Content -LiteralPath $registration
    $attempted = $true
    $registered = railway api 'mutation($input:SshPublicKeyCreateInput!){sshPublicKeyCreate(input:$input){id name fingerprint}}' --variables "@$registration" --compact | ConvertFrom-Json
    if ($LASTEXITCODE -or -not $registered.data.sshPublicKeyCreate.id) { throw 'Temporary key registration failed' }
    $data = railway ssh --project 983b8896-688f-47ea-a693-6985e84ab03b --service 128a61e8-a333-4c93-aa77-550d4e923495 --environment 7a940de4-9c13-411e-ad59-eb30ee42a9d4 --identity-file $key -- $command
    if ($LASTEXITCODE) { throw "Production volume $Action failed" }
    $result = ($data | Where-Object { $_ -match '^\{' } | Select-Object -Last 1) | ConvertFrom-Json
    if (-not $result) { throw 'Production volume receipt is missing' }
    if ($Action -in @('backup','deploy-check')) {
        $result | Add-Member -NotePropertyName releaseSha -NotePropertyValue $ExpectedSha
    }
    $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $evidence "$Action.json")
    Write-Output "Production volume $Action receipt recorded."
} finally {
    try {
        if ($attempted) {
            $keys = railway api $query --compact | ConvertFrom-Json
            if ($LASTEXITCODE -or -not $keys.data.sshPublicKeys) { throw 'Temporary key lookup failed' }
            foreach ($entry in $keys.data.sshPublicKeys.edges.node | Where-Object name -EQ $keyName) {
                $removal = railway api 'mutation($id:String!){sshPublicKeyDelete(id:$id)}' --raw-var "id=$($entry.id)" --compact | ConvertFrom-Json
                if ($LASTEXITCODE -or -not $removal.data.sshPublicKeyDelete) { throw 'Temporary key removal failed' }
            }
            $keys = railway api $query --compact | ConvertFrom-Json
            if ($LASTEXITCODE -or -not $keys.data.sshPublicKeys -or ($keys.data.sshPublicKeys.edges.node | Where-Object name -EQ $keyName)) {
                throw 'Temporary key absence could not be verified'
            }
            @{ name=$keyName; removed=$true } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence "$Action-key-removed.json")
        }
    } finally {
        foreach ($file in @($key, "$key.pub", $registration)) {
            if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force }
        }
    }
}
