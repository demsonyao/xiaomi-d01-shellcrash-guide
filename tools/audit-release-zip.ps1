[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Archive,
    [string]$SourceRoot,
    [string]$LocalDenylist
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$archivePath = (Resolve-Path -LiteralPath $Archive).Path
if (-not $SourceRoot) {
    $SourceRoot = Join-Path $PSScriptRoot '..'
}
$root = (Resolve-Path -LiteralPath $SourceRoot).Path
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

$sourceItems = @(
    (Join-Path $root '.gitattributes'),
    (Join-Path $root '.gitignore'),
    (Join-Path $root 'README.md'),
    (Join-Path $root 'THIRD_PARTY.md'),
    (Join-Path $root 'docs'),
    (Join-Path $root 'd01-overlay'),
    (Join-Path $root 'patches'),
    (Join-Path $root 'examples'),
    (Join-Path $root 'vendor'),
    (Join-Path $root 'tools')
)
$expected = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($item in $sourceItems) {
    if (Test-Path -LiteralPath $item -PathType Leaf) {
        $files = @(Get-Item -LiteralPath $item)
    } else {
        $files = @(Get-ChildItem -LiteralPath $item -Recurse -Force -File)
    }
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($root.Length).TrimStart('\', '/').Replace('\', '/')
        $expected[$relative] = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    }
}

$actual = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::OrdinalIgnoreCase)
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    foreach ($entry in $zip.Entries) {
        if ($entry.FullName.Contains('\')) {
            $failures.Add("non-portable backslash archive path: $($entry.FullName)")
        }
        $name = $entry.FullName.Replace('\', '/')
        if (-not $entry.Name) { continue }
        if ($name.StartsWith('/') -or $name -match '^[A-Za-z]:' -or ($name -split '/') -contains '..') {
            $failures.Add("unsafe archive path: $name")
        }
        if (-not $seen.Add($name)) {
            $failures.Add("duplicate archive path: $name")
        }
        $lower = $name.ToLowerInvariant()
        $leaf = [IO.Path]::GetFileName($lower)
        if ($lower -match '(^|/)(backups|private|captures|outdir|firmware|subscriptions)(/|$)') {
            $failures.Add("forbidden directory: $name")
        }
        if ($lower -match '(^|/)__pycache__(/|$)' -or $lower.EndsWith('.pyc')) {
            $failures.Add("generated Python cache: $name")
        }
        if ($leaf -in $forbiddenNames -or $leaf -match 'host_key') {
            $failures.Add("private filename: $name")
        }
        foreach ($extension in $forbiddenExtensions) {
            if ($lower.EndsWith($extension)) {
                $failures.Add("forbidden extension: $name")
            }
        }

        $hashAlgorithm = [Security.Cryptography.SHA256]::Create()
        $stream = $entry.Open()
        try {
            $hash = [BitConverter]::ToString($hashAlgorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
        } finally {
            $stream.Dispose()
            $hashAlgorithm.Dispose()
        }
        $actual[$name] = $hash

        if ($entry.Length -le 2MB -and $name -notin @('tools/audit-public.ps1', 'tools/audit-release-zip.ps1')) {
            $stream = $entry.Open()
            $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8, $true)
            try {
                $text = $reader.ReadToEnd()
            } finally {
                $reader.Dispose()
                $stream.Dispose()
            }
            $text = $text.Replace('C:\Users\<YOU>', 'C:\PLACEHOLDER')
            for ($patternIndex = 0; $patternIndex -lt $patterns.Count; $patternIndex++) {
                if ($text -match $patterns[$patternIndex]) {
                    $failures.Add("sensitive pattern rule $patternIndex in: $name")
                    break
                }
            }
        }
    }
} finally {
    $zip.Dispose()
}

foreach ($name in $expected.Keys) {
    if (-not $actual.ContainsKey($name)) {
        $failures.Add("missing from archive: $name")
    } elseif ($actual[$name] -ne $expected[$name]) {
        $failures.Add("content mismatch: $name")
    }
}
foreach ($name in $actual.Keys) {
    if (-not $expected.ContainsKey($name)) {
        $failures.Add("extra archive file: $name")
    }
}

if ($failures.Count -gt 0) {
    $failures | Sort-Object -Unique | ForEach-Object { Write-Host "RELEASE_AUDIT_FAILURE=$_" }
    throw "PUBLIC_RELEASE_AUDIT_FAILED=$($failures.Count)"
}

Write-Host "PUBLIC_RELEASE_AUDIT_OK_FILES=$($actual.Count)"
Write-Host 'ZIP_EXTRA=0 ZIP_MISSING=0 ZIP_CONTENT_MISMATCH=0'
