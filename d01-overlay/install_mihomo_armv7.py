#!/usr/bin/env python3
"""Install and validate ShellCrash's compact ARMv7 Mihomo core without starting it."""

import hashlib
import os

import gateway


CORE = os.path.abspath(
    os.path.join("..", "shellcrash-package", "cores", "mihomo-shellcrash-armv7.upx")
)
EXPECTED_SHA256 = "33d58f2103c674caaf12ac350cd351539102b6089fae0a3ce44b50fb36f86b64"
CRASHDIR = "/data/ShellCrash"
REMOTE_CORE = f"{CRASHDIR}/CrashCore.upx"


hasher = hashlib.sha256()
with open(CORE, "rb") as core_file:
    for chunk in iter(lambda: core_file.read(1024 * 1024), b""):
        hasher.update(chunk)
actual_sha256 = hasher.hexdigest()
if actual_sha256 != EXPECTED_SHA256:
    raise SystemExit(f"ERROR: Mihomo core SHA256 mismatch: {actual_sha256}")

gw = gateway.Gateway()

if gw.run_cmd(f"test -s {CRASHDIR}/menu.sh; echo $?", die_on_error=False).strip() != "0":
    raise SystemExit("ERROR: ShellCrash framework is not installed")

free_kb = gw.run_cmd("df -P /data | awk 'NR==2 {print $4}'", die_on_error=False)
try:
    free_kb_int = int((free_kb or "0").strip())
except ValueError:
    free_kb_int = 0
required_kb = (os.path.getsize(CORE) + 1023) // 1024 + 8 * 1024
if free_kb_int < required_kb:
    raise SystemExit(
        f"ERROR: /data free space {free_kb_int} KiB is below safe requirement {required_kb} KiB"
    )

print(f"Uploading compact ARMv7 Mihomo core ({actual_sha256}) ...")
if not gw.upload(CORE, REMOTE_CORE):
    raise SystemExit("ERROR: Cannot upload Mihomo core")

commands = [
    f"chmod 0755 {REMOTE_CORE}",
    f"{REMOTE_CORE} -v 2>&1 | head -n 1",
    (
        f"CRASHDIR={CRASHDIR}; CFG_PATH={CRASHDIR}/configs/ShellCrash.cfg; "
        f". {CRASHDIR}/libs/set_config.sh; "
        "setconfig cpucore armv7; setconfig crashcore meta; setconfig zip_type upx; "
        f"core_v=$({REMOTE_CORE} -v 2>/dev/null | head -n 1 | sed 's/ linux.*//;s/.* //'); "
        "setconfig core_v \"$core_v\"; setconfig custcorelink"
    ),
    (
        f"CRASHDIR={CRASHDIR}; . {CRASHDIR}/libs/set_config.sh; "
        f"setconfig BINDIR {CRASHDIR} {CRASHDIR}/configs/command.env; "
        f"setconfig TMPDIR /tmp/ShellCrash {CRASHDIR}/configs/command.env; "
        f"setconfig COMMAND '\"$TMPDIR/CrashCore -d $BINDIR -f $TMPDIR/config.yaml\"' "
        f"{CRASHDIR}/configs/command.env"
    ),
]

for command in commands:
    output = gw.run_cmd(command, die_on_error=False, timeout=45)
    print(output or "")
    if gw.errcode != 0:
        raise SystemExit(f"ERROR: Remote core installation command failed (rc={gw.errcode})")

checks = [
    f"ls -lh {REMOTE_CORE}",
    f"{REMOTE_CORE} -v 2>&1 | head -n 1",
    f"grep -E '^(cpucore|crashcore|zip_type|core_v)=' {CRASHDIR}/configs/ShellCrash.cfg",
    f"cat {CRASHDIR}/configs/command.env",
    "df -h /data /tmp",
    "pidof CrashCore 2>/dev/null || echo CORE_NOT_RUNNING",
]

for command in checks:
    print(f"\n### {command}")
    print(gw.run_cmd(command, die_on_error=False, timeout=20) or "")

print("MIHOMO_ARMV7_INSTALLED_NOT_STARTED")
