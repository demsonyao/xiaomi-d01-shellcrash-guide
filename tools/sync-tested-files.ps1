[CmdletBinding()]
param(
    [string]$XmirRoot
)

$ErrorActionPreference = 'Stop'
if (-not $XmirRoot) {
    $XmirRoot = Join-Path $PSScriptRoot '..\..\xmir-patcher'
}
$guideRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$sourceRoot = (Resolve-Path -LiteralPath $XmirRoot).Path
$overlayRoot = Join-Path $guideRoot 'd01-overlay'

$files = @(
    'enable_ssh_d01.py',
    'repair_d01_dropbear_boot.py',
    'probe_d01_tproxy_capability.py',
    'install_shellcrash_framework.py',
    'install_mihomo_armv7.py',
    'install_zashboard.py',
    'd01_failsafe.py',
    'test_start_shellcrash.py',
    'test_enable_shellcrash_firewall.py',
    'install_shellcrash_d01_boot.py',
    'install_d01_stability_monitor.py',
    'check_d01_stability_monitor.py',
    'import_d01_full_yaml.py',
    'prepare_d01_runtime_redir_host.py',
    'verify_d01_install.py',
    'export_d01_private_snapshot.py',
    'diagnose_shellcrash_start.py',
    'diagnose_d01_x_facebook.py',
    'diagnose_trojan_tun.py',
    'capture_broken_shellcrash_d01.py',
    'data\payload_ssh\dropbear_d01.init.d.sh',
    'data\payload_ssh\dropbear_d01.firewall_hook.sh',
    'data\payload_shellcrash\d01_defaults.sh',
    'data\payload_shellcrash\d01_test_failsafe.sh',
    'data\payload_shellcrash\d01_firewall_failsafe.sh',
    'data\payload_shellcrash\d01_boot_failsafe.sh',
    'data\payload_shellcrash\d01_boot_transaction.sh',
    'data\payload_shellcrash\shellcrash_d01.init.d.sh',
    'data\payload_shellcrash\d01_firewall_hook.sh',
    'data\payload_shellcrash\d01_stability_monitor.sh',
    'data\payload_shellcrash\d01_diagnose_start.sh'
)

foreach ($relative in $files) {
    $source = Join-Path $sourceRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing tested source: $source"
    }
    $destination = Join-Path $overlayRoot $relative
    $destinationDirectory = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

Write-Host "SYNCED_TESTED_FILES=$($files.Count)"
