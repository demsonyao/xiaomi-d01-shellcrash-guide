#!/usr/bin/env python3
"""Export a private, exact D01 application snapshot without printing secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import gateway


FILES = (
    ("/data/ShellCrash/yamls/config.yaml", "ShellCrash/yamls/config.yaml", True),
    ("/data/ShellCrash/yamls/user.yaml", "ShellCrash/yamls/user.yaml", False),
    ("/data/ShellCrash/configs/ShellCrash.cfg", "ShellCrash/configs/ShellCrash.cfg", True),
    ("/data/ShellCrash/cache.db", "ShellCrash/cache.db", False),
    ("/data/ShellCrash/CrashCore.upx", "ShellCrash/CrashCore.upx", True),
    ("/data/ShellCrash/geoip.metadb", "ShellCrash/geoip.metadb", False),
    ("/data/ShellCrash/ruleset/cn.mrs", "ShellCrash/ruleset/cn.mrs", False),
    ("/data/shellcrash_firewall_hook.sh", "hooks/shellcrash_firewall_hook.sh", True),
    ("/etc/init.d/shellcrash_d01", "hooks/shellcrash_d01.init", True),
    ("/data/dropbear_d01_firewall_hook.sh", "hooks/dropbear_firewall_hook.sh", True),
    ("/etc/init.d/dropbear", "hooks/dropbear.init", True),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inside_git(path: Path) -> bool:
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return True
    return False


def inside_marked_private_root(path: Path) -> bool:
    current = path.resolve()
    return any((candidate / "PRIVATE-ROOT.marker").is_file() for candidate in (current, *current.parents))


parser = argparse.ArgumentParser(description="Export private D01 state to a directory outside Git")
parser.add_argument("--output", required=True, help="private output root outside any Git repository")
args = parser.parse_args()

output_root = Path(args.output).expanduser().resolve()
if inside_git(output_root) and not inside_marked_private_root(output_root):
    raise SystemExit(
        "ERROR: output is under a Git repository and no PRIVATE-ROOT.marker protects it"
    )

stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
snapshot = output_root / f"d01-live-final-{stamp}"
snapshot.mkdir(parents=True, exist_ok=False)
notice_path = snapshot / "PRIVATE-DO-NOT-UPLOAD.txt"
notice_path.write_text(
    "PRIVATE D01 ROUTER SNAPSHOT\nContains proxy credentials and controller secrets.\n"
    "Do not upload, email, or commit this directory. Encrypt it at rest.\n",
    encoding="utf-8",
)

gw = gateway.Gateway()
health = gw.run_cmd(
    "printf 'KERNEL='; uname -r; printf 'MODEL='; nvram get model 2>/dev/null; "
    "printf 'CORE_PID='; pidof CrashCore 2>/dev/null || echo NONE; "
    "printf 'FIREWALL_REFS='; iptables-save 2>/dev/null | grep -Eic 'shellcrash|clash|mihomo'; "
    "printf 'TPROXY_RULES='; iptables-save 2>/dev/null | grep -c -- '-j TPROXY'; "
    "printf 'MANGLE_REFS='; iptables-save -t mangle 2>/dev/null | grep -Eic 'shellcrash|clash|mihomo'; "
    "printf 'AUTOSTART_LOCK='; test -f /data/ShellCrash/.dis_startup && echo ON || echo OFF; "
    "grep -E '^(core_v|redir_mod|dns_mod|firewall_mod|firewall_area|ipv6_redir)=' "
    "/data/ShellCrash/configs/ShellCrash.cfg 2>/dev/null; "
    "echo '=== FIREWALL_UCI ==='; "
    "uci show firewall.ShellCrash 2>&1 || true; "
    "uci show firewall.dropbearmulti 2>&1 || true; "
    "echo '=== RC_LINKS ==='; "
    "ls -l /etc/rc.d/S95shellcrash_d01 /etc/rc.d/K10shellcrash_d01 "
    "/etc/rc.d/S19dropbear /etc/rc.d/K50dropbear 2>&1 || true; true",
    die_on_error=False,
    timeout=30,
) or ""
if gw.errcode != 0 or "CORE_PID=NONE" in health or "AUTOSTART_LOCK=ON" in health:
    raise SystemExit("ERROR: router is not in the expected running final state; snapshot not exported")
(snapshot / "service-health.txt").write_text(health, encoding="utf-8")

manifest = [
    {
        "remote": "generated:privacy-notice",
        "local": "PRIVATE-DO-NOT-UPLOAD.txt",
        "bytes": notice_path.stat().st_size,
        "sha256": sha256(notice_path),
        "required": True,
    },
    {
        "remote": "generated:service-health",
        "local": "service-health.txt",
        "bytes": (snapshot / "service-health.txt").stat().st_size,
        "sha256": sha256(snapshot / "service-health.txt"),
        "required": True,
    },
]
missing_required = []
for remote_path, relative_path, required in FILES:
    local_path = snapshot / relative_path
    local_path.parent.mkdir(parents=True, exist_ok=True)
    exists = gw.run_cmd(
        f"test -s '{remote_path}' && echo PRESENT || echo MISSING",
        die_on_error=False,
        timeout=10,
    ) or ""
    if "PRESENT" not in exists:
        if required:
            missing_required.append(remote_path)
        continue
    if not gw.download(remote_path, str(local_path)):
        if required:
            missing_required.append(remote_path)
        continue
    manifest.append(
        {
            "remote": remote_path,
            "local": relative_path.replace("\\", "/"),
            "bytes": local_path.stat().st_size,
            "sha256": sha256(local_path),
            "required": required,
        }
    )

metadata = {
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "router": "Xiaomi D01",
    "tested_rom": "1.0.72 release",
    "privacy": "PRIVATE_DO_NOT_UPLOAD",
    "files": manifest,
    "missing_required": missing_required,
}
(snapshot / "manifest.json").write_text(
    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
(snapshot / "SHA256SUMS.txt").write_text(
    "".join(f"{item['sha256']}  {item['local']}\n" for item in manifest), encoding="utf-8"
)

if missing_required:
    print(f"PRIVATE_SNAPSHOT_INCOMPLETE_REQUIRED_MISSING={len(missing_required)}")
    print(f"PRIVATE_SNAPSHOT_PATH={snapshot}")
    raise SystemExit(2)
print(f"PRIVATE_SNAPSHOT_FILES={len(manifest)}")
print(f"PRIVATE_SNAPSHOT_PATH={snapshot}")
print("PRIVATE_SNAPSHOT_COMPLETE_DO_NOT_UPLOAD")
