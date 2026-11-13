#!/usr/bin/env python3
"""Cross-platform D01 SSH install/recovery orchestrator for XMiR-Patcher."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQUIRED = (
    "connect5.py",
    "passw.py",
    "repair_d01_dropbear_boot.py",
    "data/payload_ssh/dropbear_d01.init.d.sh",
    "data/payload_ssh/dropbear_d01.firewall_hook.sh",
)


def ensure_local_proxy_bypass(host: str) -> None:
    """Keep router HTTP/SSH traffic out of desktop VPN and HTTP proxies."""
    required = (host, "localhost", "127.0.0.1")
    current = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    entries = [item.strip() for item in current.split(",") if item.strip()]
    lowered = {item.lower() for item in entries}
    for item in required:
        if item.lower() not in lowered:
            entries.append(item)
            lowered.add(item.lower())
    value = ",".join(entries)
    os.environ["NO_PROXY"] = value
    os.environ["no_proxy"] = value
    print(f"LOCAL_PROXY_BYPASS={','.join(required)}")


def invoke(script: str, *arguments: str) -> None:
    command = [sys.executable, str(ROOT / script), *arguments]
    print(f"RUNNING={script}", flush=True)
    result = subprocess.run(command, cwd=str(ROOT), check=False)
    if result.returncode != 0:
        raise SystemExit(f"ERROR: {script} failed with exit code {result.returncode}")


parser = argparse.ArgumentParser(
    description="Enable/recover D01 SSH and install the legacy-init Dropbear persistence fix"
)
parser.add_argument(
    "--mode",
    choices=("first-install", "recover-existing", "repair-only"),
    default="first-install",
    help="first install, restart an existing Dropbear install, or only repair boot persistence",
)
args = parser.parse_args()

if sys.version_info < (3, 8):
    raise SystemExit("ERROR: Python 3.8 or newer is required")

missing = [relative for relative in REQUIRED if not (ROOT / relative).is_file()]
if missing:
    raise SystemExit("ERROR: missing required XMiR/overlay files: " + ", ".join(missing))

ensure_local_proxy_bypass("192.168.31.1")

print("D01 SSH installer attribution:")
print("- SmartController research: THALIUM / CVE-2023-26319")
print("- Xiaomi transport and base Dropbear deployment: XMiR-Patcher")
print("- D01 ARMv7, CRLF and legacy-init persistence adaptation: this project")
print(f"MODE={args.mode}")

if args.mode == "first-install":
    invoke("connect5.py")
    print("SSH is active. A unique root password is mandatory before persistence repair.")
    invoke("passw.py")
elif args.mode == "recover-existing":
    invoke("connect5.py", "--start-existing-ssh-only")
else:
    print("Skipping SmartController and password changes; using the active SSH service.")

invoke("repair_d01_dropbear_boot.py")
print("D01_SSH_INSTALL_COMPLETE")
print("Reboot verification remains a separate, deliberate step.")
