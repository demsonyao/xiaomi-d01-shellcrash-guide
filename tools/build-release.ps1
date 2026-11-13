[CmdletBinding()]
param(
    [string]$Version = '1.0.0',
    [string]$LocalDenylist,
    [string]$XmirRoot
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $XmirRoot) {
    $XmirRoot = Join-Path $root '..\xmir-patcher'
}
& (Join-Path $PSScriptRoot 'sync-tested-files.ps1') -XmirRoot $XmirRoot
$auditArguments = @{}
if ($LocalDenylist) {
    $auditArguments.LocalDenylist = $LocalDenylist
}
& (Join-Path $PSScriptRoot 'audit-public.ps1') @auditArguments

$dist = Join-Path $root 'dist'
New-Item -ItemType Directory -Path $dist -Force | Out-Null
$archive = Join-Path $dist "xiaomi-d01-shellcrash-guide-v$Version.zip"
if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}

$items = @(
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

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$sourceFiles = foreach ($item in $items) {
    if (Test-Path -LiteralPath $item -PathType Leaf) {
        Get-Item -LiteralPath $item
    } else {
        Get-ChildItem -LiteralPath $item -Recurse -Force -File
    }
}
$zip = [IO.Compression.ZipFile]::Open($archive, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($file in @($sourceFiles | Sort-Object FullName)) {
        $relative = $file.FullName.Substring($root.Length).TrimStart('\', '/').Replace('\', '/')
        $entry = $zip.CreateEntry($relative, [IO.Compression.CompressionLevel]::Optimal)
        $entry.LastWriteTime = $file.LastWriteTime
        $input = [IO.File]::OpenRead($file.FullName)
        $output = $entry.Open()
        try {
            $input.CopyTo($output)
        } finally {
            $output.Dispose()
            $input.Dispose()
        }
    }
} finally {
    $zip.Dispose()
}
& (Join-Path $PSScriptRoot 'audit-release-zip.ps1') `
    -Archive $archive -SourceRoot $root @auditArguments
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$archive.sha256" -Value "$hash  $([IO.Path]::GetFileName($archive))" -Encoding ascii
Write-Host "PUBLIC_RELEASE=$archive"
Write-Host "PUBLIC_RELEASE_SHA256=$hash"
