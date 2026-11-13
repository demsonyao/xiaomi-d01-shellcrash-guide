#!/usr/bin/env python3
"""Capture a broken D01 ShellCrash installation before repair or reinstall."""

from datetime import datetime
import hashlib
import os
import tarfile

import gateway


CRASHDIR = "/data/ShellCrash"
REMOTE_ARCHIVE = "/tmp/d01-shellcrash-broken.tar.gz"
REMOTE_REPORT = "/tmp/d01-shellcrash-broken-report.txt"


def run(gw, command, timeout=30, required=True, show=True):
    output = gw.run_cmd(command, die_on_error=False, timeout=timeout) or ""
    if show and output:
        print(output)
    if required and gw.errcode != 0:
        raise RuntimeError(f"Router command failed (rc={gw.errcode})")
    return output, gw.errcode


backup_dir = os.path.abspath("backups")
os.makedirs(backup_dir, exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
local_archive = os.path.join(backup_dir, f"d01-shellcrash-broken-{stamp}.tar.gz")

gw = gateway.Gateway()

try:
    capability, _ = run(
        gw,
        "echo CAPTURE_PREFLIGHT_OK; "
        "printf 'KERNEL='; uname -r; "
        "test -c /dev/net/tun && echo TUN_DEVICE=YES || echo TUN_DEVICE=NO; "
        "printf 'TPROXY_TARGET='; "
        "iptables -t mangle -j TPROXY -h >/dev/null 2>&1 && echo YES || echo NO; "
        "printf 'CORE_PID='; pidof CrashCore 2>/dev/null || echo NONE; "
        "printf 'FIREWALL_REFS='; iptables-save 2>/dev/null | "
        "grep -Eic 'shellcrash|clash|mihomo'; "
        f"grep -E '^(redir_mod|firewall_area|dns_mod|firewall_mod|ipv6_redir|core_v)=' "
        f"{CRASHDIR}/configs/ShellCrash.cfg 2>/dev/null; "
        "df -h /data /tmp",
        timeout=30,
    )
    if "CAPTURE_PREFLIGHT_OK" not in capability:
        raise RuntimeError("capture preflight failed")

    tmp_free_output, _ = run(
        gw,
        "df -P /tmp | awk 'NR==2 {print $4}'",
        timeout=15,
        show=False,
    )
    try:
        tmp_free_kb = int(tmp_free_output.strip())
    except ValueError:
        tmp_free_kb = 0
    if tmp_free_kb < 24 * 1024:
        raise RuntimeError(f"/tmp has only {tmp_free_kb} KiB free; full capture was not attempted")

    report_command = (
        f"rm -f {REMOTE_REPORT} {REMOTE_ARCHIVE}; "
        "{ "
        "echo 'D01_BROKEN_SHELLCRASH_CAPTURE_V1'; date; uname -a; "
        "echo '=== PROCESS ==='; ps w 2>&1; "
        "echo '=== MEMORY ==='; cat /proc/meminfo 2>&1; "
        "echo '=== FILESYSTEM ==='; df -h /data /tmp 2>&1; "
        "echo '=== SHELLCRASH_STATUS ==='; "
        "printf 'CORE_PID='; pidof CrashCore 2>/dev/null || echo NONE; "
        "printf 'FIREWALL_REFS='; iptables-save 2>/dev/null | "
        "grep -Eic 'shellcrash|clash|mihomo'; "
        f"ls -ld {CRASHDIR} {CRASHDIR}/CrashCore* {CRASHDIR}/yamls "
        f"{CRASHDIR}/configs/ShellCrash.cfg /tmp/ShellCrash 2>&1; "
        "echo '=== FIREWALL_UCI ==='; uci show firewall.ShellCrash 2>&1; "
        "echo '=== IPTABLES_REFS ==='; iptables-save 2>/dev/null | "
        "grep -Ei 'shellcrash|clash|mihomo' | sed -E "
        "'s/([0-9]{1,3}\\.){3}[0-9]{1,3}/<ip>/g' | head -n 250; "
        "echo '=== KERNEL_EVIDENCE ==='; dmesg 2>/dev/null | "
        "grep -Ei 'out of memory|oom-killer|killed process|nf_conntrack.*table full|CrashCore' | tail -n 120; "
        "echo '=== SYSTEM_LOG ==='; logread 2>/dev/null | "
        "grep -Ei 'shellcrash|CrashCore|mihomo|out of memory|oom|conntrack' | tail -n 200; "
        f"}} >{REMOTE_REPORT} 2>&1; chmod 0600 {REMOTE_REPORT}; "
        "echo CAPTURE_REPORT_READY"
    )
    report, report_rc = run(gw, report_command, timeout=45, required=False)
    if report_rc != 0 or "CAPTURE_REPORT_READY" not in report:
        raise RuntimeError("could not create the diagnostic report")

    archive_command = (
        "paths='tmp/d01-shellcrash-broken-report.txt'; "
        "for path in data/ShellCrash data/shellcrash_init.sh "
        "data/shellcrash_firewall_hook.sh data/auto_start.sh data/d01-stability "
        "etc/init.d/shellcrash_d01 etc/rc.d/S95shellcrash_d01 etc/rc.d/K10shellcrash_d01; do "
        "test -e /$path && paths=\"$paths $path\"; done; "
        f"tar -czf {REMOTE_ARCHIVE} -C / $paths 2>/tmp/d01-shellcrash-capture-tar.stderr; "
        "rc=$?; "
        f"test -s {REMOTE_ARCHIVE} || exit 1; "
        f"chmod 0600 {REMOTE_ARCHIVE}; "
        f"printf 'REMOTE_CAPTURE_BYTES='; wc -c <{REMOTE_ARCHIVE}; "
        "echo TAR_RC=$rc; exit 0"
    )
    archive, archive_rc = run(gw, archive_command, timeout=150, required=False)
    if archive_rc != 0 or "REMOTE_CAPTURE_BYTES=" not in archive:
        raise RuntimeError("could not create the ShellCrash backup archive")

    if not gw.download(REMOTE_ARCHIVE, local_archive, verbose=1):
        raise RuntimeError("cannot download the ShellCrash backup archive")

    if not os.path.isfile(local_archive) or os.path.getsize(local_archive) < 1024:
        raise RuntimeError("downloaded ShellCrash backup is unexpectedly small")
    with tarfile.open(local_archive, "r:gz") as archive_file:
        members = archive_file.getmembers()
    if not members or not any(member.name.startswith("data/ShellCrash/") for member in members):
        raise RuntimeError("downloaded archive does not contain /data/ShellCrash")

    hasher = hashlib.sha256()
    with open(local_archive, "rb") as backup_file:
        for chunk in iter(lambda: backup_file.read(1024 * 1024), b""):
            hasher.update(chunk)

    run(
        gw,
        f"rm -f {REMOTE_ARCHIVE} {REMOTE_REPORT} "
        "/tmp/d01-shellcrash-capture-tar.stderr",
        timeout=20,
        required=False,
        show=False,
    )
    print(f"LOCAL_CAPTURE={local_archive}")
    print(f"LOCAL_CAPTURE_BYTES={os.path.getsize(local_archive)}")
    print(f"LOCAL_CAPTURE_FILES={len(members)}")
    print(f"LOCAL_CAPTURE_SHA256={hasher.hexdigest()}")
    print("BROKEN_SHELLCRASH_CAPTURE_COMPLETE_NO_ROUTER_CHANGES")
except Exception as error:
    run(
        gw,
        f"rm -f {REMOTE_ARCHIVE} {REMOTE_REPORT}",
        timeout=20,
        required=False,
        show=False,
    )
    print(f"BROKEN_SHELLCRASH_CAPTURE_FAILED: {error}")
    raise SystemExit(2)

