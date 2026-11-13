#!/usr/bin/env python3
"""Install the reviewed ShellCrash 1.9.4 framework on Xiaomi D01."""

import hashlib
import os

import gateway


PACKAGE = os.path.abspath(os.path.join("..", "shellcrash-package", "ShellCrash.tar.gz"))
EXPECTED_SHA256 = "4f946031a0483ed528e266143d459075489cce6c3f8f2f4681f39ca6d7448681"
REMOTE_PACKAGE = "/tmp/ShellCrash.tar.gz"
CRASHDIR = "/data/ShellCrash"
STABLE_URL = "https://testingcf.jsdelivr.net/gh/juewuy/ShellCrash@stable"


hasher = hashlib.sha256()
with open(PACKAGE, "rb") as package_file:
    for chunk in iter(lambda: package_file.read(1024 * 1024), b""):
        hasher.update(chunk)
actual_sha256 = hasher.hexdigest()
if actual_sha256 != EXPECTED_SHA256:
    raise SystemExit(f"ERROR: ShellCrash package SHA256 mismatch: {actual_sha256}")

gw = gateway.Gateway()

free_kb = gw.run_cmd("df -P /data | awk 'NR==2 {print $4}'", die_on_error=False)
try:
    free_kb_int = int((free_kb or "0").strip())
except ValueError:
    free_kb_int = 0
if free_kb_int < 20 * 1024:
    raise SystemExit(f"ERROR: /data has only {free_kb_int} KiB free; installation aborted")

if gw.run_cmd("test -e /data/ShellCrash -o -e /data/clash; echo $?", die_on_error=False).strip() != "1":
    raise SystemExit("ERROR: Existing /data/ShellCrash or /data/clash detected; installation aborted")

print(f"Uploading reviewed ShellCrash package ({actual_sha256}) ...")
if not gw.upload(PACKAGE, REMOTE_PACKAGE):
    raise SystemExit("ERROR: Cannot upload ShellCrash package")

commands = [
    f"mkdir -p {CRASHDIR}; tar -zxf {REMOTE_PACKAGE} -C {CRASHDIR}",
    (
        f"CRASHDIR={CRASHDIR}; my_alias=crash; url='{STABLE_URL}'; "
        "release_type=stable; language=chs; "
        "export CRASHDIR my_alias url release_type language; "
        f". {CRASHDIR}/init.sh"
    ),
    f"rm -f {REMOTE_PACKAGE}",
]

for command in commands:
    output = gw.run_cmd(command, die_on_error=False, timeout=60)
    print(output or "")
    if gw.errcode != 0:
        raise SystemExit(f"ERROR: Remote installation command failed (rc={gw.errcode})")

checks = [
    f"test -s {CRASHDIR}/menu.sh && echo FRAMEWORK_OK",
    f"grep -E '^(versionsh_l|release_type|systype|cpucore)=' {CRASHDIR}/configs/ShellCrash.cfg 2>/dev/null",
    "uci show firewall.ShellCrash 2>&1",
    "ls -l /data/shellcrash_init.sh /data/auto_start.sh 2>&1",
    "df -h /data",
    "pidof CrashCore 2>/dev/null || echo CORE_NOT_RUNNING",
]

for command in checks:
    print(f"\n### {command}")
    print(gw.run_cmd(command, die_on_error=False, timeout=15) or "")

print("SHELLCRASH_FRAMEWORK_INSTALLED")
