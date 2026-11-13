#!/usr/bin/env python3
"""Repair D01 Dropbear persistence without restarting the active SSH daemon."""

import os

from gateway import create_gateway


XDIR = "/etc/crontabs/dropbearmulti"
SOURCE_INIT = f"{XDIR}/init.d01.sh"
TARGET_INIT = "/etc/init.d/dropbear"
HOOK = "/data/dropbear_d01_firewall_hook.sh"
REMOTE_INIT = "/tmp/dropbear_d01.init"
REMOTE_HOOK = "/tmp/dropbear_d01.firewall_hook"


def run(gw, command, timeout=25, required=True):
    output = gw.run_cmd(command, die_on_error=False, timeout=timeout) or ""
    if output:
        print(output)
    if required and gw.errcode != 0:
        raise RuntimeError(f"Router command failed (rc={gw.errcode})")
    return output, gw.errcode


gw = create_gateway(
    timeout=4,
    die_if_sshOk=False,
    die_if_ftpOk=False,
    web_login=False,
    try_telnet=False,
)

try:
    preflight, _ = run(
        gw,
        f"test -x {XDIR}/dropbear && pidof dropbear >/dev/null 2>&1 && "
        "netstat -lnt 2>/dev/null | grep -q ':22 ' && echo DROPBEAR_REPAIR_PREFLIGHT_OK",
    )
    if "DROPBEAR_REPAIR_PREFLIGHT_OK" not in preflight:
        raise RuntimeError("the recovered SSH daemon is not healthy")

    previous_path, _ = run(
        gw,
        "printf 'PREVIOUS_FIREWALL_HOOK='; uci -q get firewall.dropbearmulti.path || echo MISSING; "
        "printf 'PID1='; cat /proc/1/comm",
        required=False,
    )
    if "install.sh" in previous_path and "PID1=procd" not in previous_path:
        print("CAUSE_CONFIRMED=GENERIC_PROCD_INSTALLER_ON_LEGACY_INIT")

    payloads = (
        (os.path.join("data", "payload_ssh", "dropbear_d01.init.d.sh"), REMOTE_INIT),
        (os.path.join("data", "payload_ssh", "dropbear_d01.firewall_hook.sh"), REMOTE_HOOK),
    )
    for local_path, remote_path in payloads:
        if not gw.upload(local_path, remote_path):
            raise RuntimeError(f"cannot upload {os.path.basename(local_path)}")

    print("Installing the D01 legacy init source and idempotent boot hook ...")
    stages = (
        (
            "NORMALIZE_UPLOADS",
            f"for f in {REMOTE_INIT} {REMOTE_HOOK}; do "
            "tr -d '\\r' < \"$f\" > \"$f.lf\" && mv -f \"$f.lf\" \"$f\"; done",
        ),
        (
            "BACKUP_PREVIOUS_INIT",
            f"test -s {XDIR}/init.before-d01-repair || "
            f"cp -p {TARGET_INIT} {XDIR}/init.before-d01-repair 2>/dev/null || true",
        ),
        (
            "INSTALL_D01_INIT",
            f"cp -f {REMOTE_INIT} {SOURCE_INIT}; cp -f {REMOTE_INIT} {TARGET_INIT}; "
            f"chmod 0755 {SOURCE_INIT} {TARGET_INIT}",
        ),
        (
            "INSTALL_SAFE_HOOK",
            f"cp -f {REMOTE_HOOK} {HOOK}; chmod 0755 {HOOK}",
        ),
        (
            "INSTALL_RC_LINKS",
            "rm -f /etc/rc.d/S19dropbear /etc/rc.d/K50dropbear; "
            "ln -s ../init.d/dropbear /etc/rc.d/S19dropbear; "
            "ln -s ../init.d/dropbear /etc/rc.d/K50dropbear",
        ),
        (
            "REGISTER_SAFE_FIREWALL_HOOK",
            "uci set firewall.dropbearmulti=include; "
            "uci set firewall.dropbearmulti.type='script'; "
            f"uci set firewall.dropbearmulti.path='{HOOK}'; "
            "uci set firewall.dropbearmulti.enabled='1'; uci commit firewall",
        ),
        ("CLEAN_TEMP_FILES", f"rm -f {REMOTE_INIT} {REMOTE_HOOK}"),
    )
    current_stage = "UNKNOWN"
    for current_stage, command in stages:
        print(f"REPAIR_STAGE={current_stage}")
        run(gw, command)

    checks, checks_rc = run(
        gw,
        f"cmp -s {SOURCE_INIT} {TARGET_INIT} && "
        f"test -x {HOOK} && "
        f"test \"$(uci -q get firewall.dropbearmulti.path)\" = \"{HOOK}\" && "
        "test \"$(uci -q get firewall.dropbearmulti.enabled)\" = '1' && "
        "pidof dropbear >/dev/null 2>&1 && "
        "netstat -lnt 2>/dev/null | grep -q ':22 ' && "
        "echo D01_DROPBEAR_BOOT_REPAIRED_NO_RESTART; "
        "ls -l /etc/rc.d/S19dropbear /etc/rc.d/K50dropbear 2>&1; "
        "uci show firewall.dropbearmulti",
        required=False,
    )
    if checks_rc != 0 or "D01_DROPBEAR_BOOT_REPAIRED_NO_RESTART" not in checks:
        raise RuntimeError("installed boot files did not validate")

    print("ACTIVE_SSH_PROCESS_UNCHANGED")
except Exception as error:
    stage = locals().get("current_stage", "PREFLIGHT_OR_UPLOAD")
    print(f"DROPBEAR_BOOT_REPAIR_FAILED_AT={stage}: {error}")
    print("The currently running SSH daemon was not intentionally restarted.")
    raise SystemExit(2)
