#!/usr/bin/env python3
"""Install and start a low-overhead, non-autostart D01 stability monitor."""

import hashlib
import os
import time

import gateway


CRASHDIR = "/data/ShellCrash"
BASE = "/data/d01-stability"
RUNDIR = "/tmp/d01-stability"
REMOTE_TEMP = "/tmp/d01_stability_monitor.candidate.sh"
REMOTE_MONITOR = f"{BASE}/monitor.sh"
LOCAL_MONITOR = os.path.join("data", "payload_shellcrash", "d01_stability_monitor.sh")


def run(gw, command, timeout=30, required=True, show=True):
    output = gw.run_cmd(command, die_on_error=False, timeout=timeout) or ""
    if show and output:
        print(output)
    if required and gw.errcode != 0:
        raise RuntimeError(f"Router command failed (rc={gw.errcode})")
    return output, gw.errcode


with open(LOCAL_MONITOR, "rb") as source_file:
    local_bytes = source_file.read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
local_sha256 = hashlib.sha256(local_bytes).hexdigest()
local_size = len(local_bytes)

gw = gateway.Gateway()

try:
    preflight, _ = run(
        gw,
        f"test -x {CRASHDIR}/CrashCore.upx && pidof CrashCore >/dev/null 2>&1 && "
        "test $(iptables-save 2>/dev/null | grep -Eic 'shellcrash|clash|mihomo') -gt 0 && "
        "command -v awk >/dev/null && command -v curl >/dev/null && "
        "command -v iptables-save >/dev/null && command -v logread >/dev/null && "
        "test $(df -P /data | awk 'NR==2 {print $4}') -gt 512 && "
        "echo MONITOR_PREFLIGHT_OK",
        timeout=25,
    )
    if "MONITOR_PREFLIGHT_OK" not in preflight:
        raise RuntimeError("router service or monitoring command preflight failed")

    existing, _ = run(
        gw,
        f"if test -s {RUNDIR}/monitor.pid; then "
        f"pid=$(cat {RUNDIR}/monitor.pid); "
        "if kill -0 \"$pid\" 2>/dev/null && "
        f"tr '\\000' ' ' </proc/$pid/cmdline 2>/dev/null | grep -q '{REMOTE_MONITOR} run'; then "
        "echo EXISTING_MONITOR_PID=$pid; fi; fi",
        timeout=15,
        required=False,
    )
    if "EXISTING_MONITOR_PID=" in existing:
        print(existing.strip())
        run(gw, f"{REMOTE_MONITOR} status", timeout=15, required=False)
        print("D01_STABILITY_MONITOR_ALREADY_RUNNING_NO_CHANGES")
        raise SystemExit(0)

    print(f"Uploading reviewed stability monitor ({local_sha256}) ...")
    if not gw.upload(LOCAL_MONITOR, REMOTE_TEMP):
        raise RuntimeError("cannot upload stability monitor")

    normalized, normalized_rc = run(
        gw,
        f"tr -d '\\r' < {REMOTE_TEMP} > {REMOTE_TEMP}.lf && "
        f"mv -f {REMOTE_TEMP}.lf {REMOTE_TEMP}; chmod 0700 {REMOTE_TEMP}; "
        "echo MONITOR_UPLOAD_NORMALIZED",
        timeout=20,
        required=False,
    )
    if normalized_rc != 0 or "MONITOR_UPLOAD_NORMALIZED" not in normalized:
        raise RuntimeError(f"monitor line-ending normalization failed (rc={normalized_rc})")

    remote_hash, remote_hash_rc = run(
        gw,
        f"hash=$(sha256sum {REMOTE_TEMP} 2>/dev/null | awk '{{print $1}}'); "
        "if test -n \"$hash\"; then echo SHA256=$hash; "
        f"else printf 'SIZE='; wc -c <{REMOTE_TEMP}; fi",
        timeout=15,
        required=False,
    )
    verification = remote_hash.strip().splitlines()[-1] if remote_hash.strip() else ""
    if verification.startswith("SHA256="):
        actual_remote_hash = verification.split("=", 1)[1].strip().lower()
        if remote_hash_rc != 0 or actual_remote_hash != local_sha256:
            raise RuntimeError(
                f"monitor SHA256 mismatch (expected={local_sha256}, actual={actual_remote_hash or 'missing'})"
            )
        print("MONITOR_REMOTE_SHA256_OK")
    elif verification.startswith("SIZE="):
        try:
            actual_remote_size = int(verification.split("=", 1)[1].strip())
        except ValueError:
            actual_remote_size = -1
        if remote_hash_rc != 0 or actual_remote_size != local_size:
            raise RuntimeError(
                f"monitor size mismatch (expected={local_size}, actual={actual_remote_size})"
            )
        print("MONITOR_REMOTE_SIZE_OK_SHA256SUM_UNAVAILABLE")
    else:
        raise RuntimeError(f"monitor remote integrity check produced no usable result (rc={remote_hash_rc})")

    syntax, syntax_rc = run(
        gw,
        f"sh -n {REMOTE_TEMP} 2>&1; rc=$?; echo MONITOR_SH_N_RC=$rc; exit $rc",
        timeout=20,
        required=False,
    )
    if syntax_rc != 0:
        detail = " | ".join(line[:240] for line in syntax.splitlines()[-6:])
        raise RuntimeError(f"monitor BusyBox shell syntax check failed: {detail}")
    print("MONITOR_BUSYBOX_SYNTAX_OK")

    installed, installed_rc = run(
        gw,
        f"mkdir -p {BASE} {RUNDIR} && chmod 0700 {BASE} {RUNDIR} && "
        f"mv -f {REMOTE_TEMP} {REMOTE_MONITOR} && chmod 0700 {REMOTE_MONITOR} && "
        "echo MONITOR_FILE_INSTALLED",
        timeout=25,
        required=False,
    )
    if installed_rc != 0 or "MONITOR_FILE_INSTALLED" not in installed:
        raise RuntimeError("monitor hash verification or installation failed")

    started, started_rc = run(
        gw,
        f"rm -f {RUNDIR}/triggered {RUNDIR}/maintenance; "
        f"nohup {REMOTE_MONITOR} run >{RUNDIR}/monitor.log 2>&1 & "
        f"echo $! >{RUNDIR}/launcher.pid; echo MONITOR_LAUNCHED",
        timeout=15,
        required=False,
    )
    if started_rc != 0 or "MONITOR_LAUNCHED" not in started:
        raise RuntimeError("cannot launch stability monitor")

    time.sleep(4)
    status, status_rc = run(
        gw,
        f"{REMOTE_MONITOR} status; "
        f"ls -lh {REMOTE_MONITOR} {RUNDIR}/ring.0.csv 2>&1; "
        f"test ! -e /etc/rc.d/S*d01-stability && "
        "echo NO_AUTOSTART_NO_ROUTING_CHANGES",
        timeout=20,
        required=False,
    )
    if status_rc != 0 or "MONITOR_RUNNING_PID=" not in status:
        raise RuntimeError("monitor process did not remain running")
    print("D01_STABILITY_MONITOR_RUNNING")
    print(f"TRIGGER_SNAPSHOT_PATH={BASE}/last-trigger.txt")
except SystemExit:
    raise
except Exception as error:
    run(gw, f"rm -f {REMOTE_TEMP} {REMOTE_TEMP}.lf", required=False, show=False)
    print(f"D01_STABILITY_MONITOR_INSTALL_FAILED: {error}")
    raise SystemExit(2)
