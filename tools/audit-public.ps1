[CmdletBinding()]
param(
    [string]$LocalDenylist
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$failures = [System.Collections.Generic.List[string]]::new()

$forbiddenExtensions = @(
    '.bin', '.ubi', '.img', '.upx', '.db', '.metadb', '.mrs', '.tar.gz',
    '.key', '.pem', '.zip', '.7z', '.tgz', '.gz', '.pcap', '.pcapng',
    '.sqlite', '.sqlite3'
)
$forbiddenNames = @(
    'config.yaml', 'user.yaml', 'shellcrash.cfg', 'cache.db', 'authorized_keys',
    'id_rsa', 'id_ed25519', 'shadow', 'shadow-', 'chap-secrets', 'xl2tp-secrets'
)
$files = Get-ChildItem -LiteralPath $root -Recurse -Force -File |
    Where-Object { $_.FullName -notmatch '[\\/]dist[\\/]' }

foreach ($file in $files) {
    $relative = $file.FullName.Substring($root.Length).TrimStart('\', '/')
    $lower = $relative.ToLowerInvariant()
    if ($lower -match '(^|[\\/])(backups|private|captures|outdir|firmware|subscriptions)([\\/]|$)') {
        $failures.Add("forbidden directory: $relative")
    }
    if ($lower -match '(^|[\\/])__pycache__([\\/]|$)' -or $lower.EndsWith('.pyc')) {
        $failures.Add("generated Python cache: $relative")
    }
    $leaf = [IO.Path]::GetFileName($lower)
    if ($leaf -in $forbiddenNames -or $leaf -match 'host_key') {
        $failures.Add("private configuration filename: $relative")
    }
    foreach ($extension in $forbiddenExtensions) {
        if ($lower.EndsWith($extension)) {
            $failures.Add("forbidden binary/private extension: $relative")
        }
    }
}

$patterns = @(
    '(?i)(trojan|vless|vmess|ssr?|hysteria2|hy2)://',
    '-----BEGIN [A-Z ]*PRIVATE KEY-----',
    '(?i)C:\\Users\\[^\\\r\n]+',
    '(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b',
    '(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b',
    '(?im)^\s*(?:password|passwd|secret|token|authorization|private-key)\s*:\s*(?!$|[<{\[]|[''"]?(?:example|your|configured))\S+',
    '(?im)^\s*(?:server|sni)\s*:\s*(?!$|[<{\[]|[''"]?(?:example\.com|localhost|127\.0\.0\.1))\S+',
    '(?i)https?://[^\s)''"]+(?:token|key|auth|subscription|client_id)=[^\s)''"]+'
)

if ($LocalDenylist) {
    $denylistPath = (Resolve-Path -LiteralPath $LocalDenylist).Path
    foreach ($line in Get-Content -LiteralPath $denylistPath -Encoding UTF8) {
        $value = $line.Trim()
        if ($value -and -not $value.StartsWith('#')) {
            $patterns += [regex]::Escape($value)
        }
    }
}

foreach ($file in $files) {
    if ($file.Length -gt 2MB) { continue }
    $relative = $file.FullName.Substring($root.Length).TrimStart('\', '/')
    if ($relative -in @('tools\audit-public.ps1', 'tools\audit-release-zip.ps1')) { continue }
    $text = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($null -eq $text) { continue }
    $text = $text.Replace('C:\Users\<YOU>', 'C:\PLACEHOLDER')
    for ($patternIndex = 0; $patternIndex -lt $patterns.Count; $patternIndex++) {
        if ($text -match $patterns[$patternIndex]) {
            $failures.Add("sensitive pattern rule $patternIndex in: $relative")
            break
        }
    }
}

if ($failures.Count -gt 0) {
    $failures | Sort-Object -Unique | ForEach-Object { Write-Host "AUDIT_FAILURE=$_" }
    throw "PUBLIC_AUDIT_FAILED=$($failures.Count)"
}

Write-Host "PUBLIC_AUDIT_OK_FILES=$($files.Count)"
