#!/usr/bin/env python3
"""Install and validate a D01-compatible ShellCrash boot service."""

import os
import time

import requests

import gateway
from d01_failsafe import RouterFailsafe


CRASHDIR = "/data/ShellCrash"
INIT_PATH = "/etc/init.d/shellcrash_d01"
HOOK_PATH = "/data/shellcrash_firewall_hook.sh"
REMOTE_INIT = "/tmp/shellcrash_d01.init"
REMOTE_HOOK = "/tmp/shellcrash_d01_firewall_hook.sh"
REMOTE_FAILSAFE = "/tmp/shellcrash_d01_boot_failsafe.sh"
REMOTE_BOOT_TRANSACTION = "/tmp/d01_boot_transaction.sh"
DASHBOARD_URL = "http://192.168.31.1:9999/ui/"


def run(gw, command, timeout=30, required=True):
    output = gw.run_cmd(command, die_on_error=False, timeout=timeout) or ""
    if output:
        print(output)
    if required and gw.errcode != 0:
        raise RuntimeError(f"Router command failed (rc={gw.errcode})")
    return output, gw.errcode


def firewall_count(gw):
    output, rc = run(
        gw,
        "command -v iptables-save >/dev/null 2>&1 || exit 1; "
        "rules=$(iptables-save 2>/dev/null) || exit 1; "
        "printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true",
        timeout=12,
        required=False,
    )
    if rc != 0:
        return None
    try:
        return int(output.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def rollback(gw, failsafe, reason):
    print(f"D01_BOOT_TEST_FAILED: {reason}")
    print("Requesting the independent router watchdog to restore direct routing and boot state ...")
    if failsafe.request_rollback():
        print("ROUTER_WATCHDOG_ROLLBACK_COMPLETED")
    else:
        print("ROUTER_WATCHDOG_ROLLBACK_REQUIRES_INSPECTION")
    raise SystemExit(2)


gw = gateway.Gateway()
service_test_started = False
failsafe = None

try:
    preflight, _ = run(
        gw,
        f"test -f {CRASHDIR}/.dis_startup && test -s {CRASHDIR}/yamls/config.yaml && "
        f"test -x {CRASHDIR}/CrashCore.upx && command -v iptables-save >/dev/null 2>&1 && "
        "rules=$(iptables-save 2>/dev/null) && "
        "refs=$(printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true) && "
        "if pidof CrashCore >/dev/null 2>&1; then test \"${refs:-0}\" -gt 0; "
        "else test \"${refs:-0}\" -eq 0; fi && echo BOOT_INSTALL_PREFLIGHT_OK",
    )
    if "BOOT_INSTALL_PREFLIGHT_OK" not in preflight:
        raise RuntimeError("core/rules state, persistent config, or autostart safety lock is invalid")
    failsafe = RouterFailsafe(
        lambda command, timeout=30, required=True: run(
            gw, command, timeout=timeout, required=required
        ),
        REMOTE_FAILSAFE,
        "boot-install-test",
        "/tmp/shellcrash_d01_boot_failsafe.out",
        "BOOT_FAILSAFE_ARMED_300_SECONDS",
    )
    failsafe.reserve()
    recheck, _ = run(
        gw,
        f"test -f {CRASHDIR}/.dis_startup && test -s {CRASHDIR}/yamls/config.yaml && "
        f"test -x {CRASHDIR}/CrashCore.upx && command -v iptables-save >/dev/null 2>&1 && "
        "rules=$(iptables-save 2>/dev/null) && "
        "refs=$(printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true) && "
        "if pidof CrashCore >/dev/null 2>&1; then test \"${refs:-0}\" -gt 0; "
        "else test \"${refs:-0}\" -eq 0; fi && echo RESERVED_PREFLIGHT_OK",
    )
    if "RESERVED_PREFLIGHT_OK" not in recheck:
        raise RuntimeError("router state changed while reserving the boot-install transaction")

    payloads = (
        (os.path.join("data", "payload_shellcrash", "shellcrash_d01.init.d.sh"), REMOTE_INIT),
        (os.path.join("data", "payload_shellcrash", "d01_firewall_hook.sh"), REMOTE_HOOK),
        (os.path.join("data", "payload_shellcrash", "d01_boot_failsafe.sh"), REMOTE_FAILSAFE),
        (os.path.join("data", "payload_shellcrash", "d01_boot_transaction.sh"), REMOTE_BOOT_TRANSACTION),
    )
    for local_path, remote_path in payloads:
        if not gw.upload(local_path, remote_path):
            raise RuntimeError(f"cannot upload {os.path.basename(local_path)}")

    normalization_commands = [
        f"tr -d '\\r' < {REMOTE_INIT} > {REMOTE_INIT}.lf && mv -f {REMOTE_INIT}.lf {REMOTE_INIT}",
        f"tr -d '\\r' < {REMOTE_HOOK} > {REMOTE_HOOK}.lf && mv -f {REMOTE_HOOK}.lf {REMOTE_HOOK}",
        f"tr -d '\\r' < {REMOTE_FAILSAFE} > {REMOTE_FAILSAFE}.lf && mv -f {REMOTE_FAILSAFE}.lf {REMOTE_FAILSAFE}",
        f"tr -d '\\r' < {REMOTE_BOOT_TRANSACTION} > {REMOTE_BOOT_TRANSACTION}.lf && mv -f {REMOTE_BOOT_TRANSACTION}.lf {REMOTE_BOOT_TRANSACTION}",
        f"sh -n {REMOTE_INIT} && sh -n {REMOTE_HOOK} && sh -n {REMOTE_FAILSAFE} && "
        f"sh -n {REMOTE_BOOT_TRANSACTION} && echo D01_BOOT_SHELL_SYNTAX_OK",
        f"chmod 0700 {REMOTE_FAILSAFE} {REMOTE_BOOT_TRANSACTION}",
    ]
    for command in normalization_commands:
        run(gw, command, timeout=40)

    if not failsafe.arm():
        if not failsafe.release(allow_mutated=False, require_armed=False):
            print("UNMUTATED_TRANSACTION_RETAINED_FOR_INSPECTION")
        raise RuntimeError("boot failsafe could not be armed; persistent installation was not started")
    snapshot, snapshot_rc = run(
        gw,
        f"{REMOTE_BOOT_TRANSACTION} snapshot {failsafe.token}",
        timeout=40,
        required=False,
    )
    if snapshot_rc != 0 or "BOOT_PERSISTENT_STATE_SNAPSHOTTED" not in snapshot:
        if not failsafe.release(allow_mutated=False, require_armed=True):
            print("UNMUTATED_TRANSACTION_RETAINED_FOR_INSPECTION")
        raise RuntimeError("could not snapshot the previous boot-registration state")
    if not failsafe.mark_mutation():
        if not failsafe.release(allow_mutated=False, require_armed=True):
            print("UNMUTATED_TRANSACTION_RETAINED_FOR_INSPECTION")
        raise RuntimeError("could not authorize the boot-install mutation")
    service_test_started = True

    print("Installing D01 legacy init service and safe firewall hook ...")
    install_commands = [
        f"cp -f {REMOTE_INIT} {INIT_PATH} && chmod 0755 {INIT_PATH}",
        f"cp -f {REMOTE_HOOK} {HOOK_PATH} && chmod 0755 {HOOK_PATH}",
        "if test -f /data/auto_start.sh; then "
        "sed -i '/shellcrash_init\\.sh/d' /data/auto_start.sh && "
        "! grep -q 'shellcrash_init\\.sh' /data/auto_start.sh; fi",
        f"rm -f /etc/rc.d/S95shellcrash_d01 /etc/rc.d/K10shellcrash_d01 && "
        f"ln -s ../init.d/shellcrash_d01 /etc/rc.d/S95shellcrash_d01 && "
        f"ln -s ../init.d/shellcrash_d01 /etc/rc.d/K10shellcrash_d01",
        "uci set firewall.ShellCrash=include && uci set firewall.ShellCrash.type='script' && "
        f"uci set firewall.ShellCrash.path='{HOOK_PATH}' && "
        "uci set firewall.ShellCrash.enabled='1' && uci commit firewall",
    ]
    for command in install_commands:
        run(gw, command, timeout=40)

    installed, _ = run(
        gw,
        f"test -x {INIT_PATH} && test -x {HOOK_PATH} && "
        "test -L /etc/rc.d/S95shellcrash_d01 && test -L /etc/rc.d/K10shellcrash_d01 && "
        f"test \"$(uci get firewall.ShellCrash.path)\" = \"{HOOK_PATH}\" && "
        "echo D01_BOOT_FILES_INSTALLED",
    )
    if "D01_BOOT_FILES_INSTALLED" not in installed:
        raise RuntimeError("boot files or firewall hook registration did not validate")

    print("Testing stop through the D01 init service ...")
    run(gw, f"{INIT_PATH} stop", timeout=90, required=False)
    stopped, _ = run(
        gw,
        "pidof CrashCore 2>/dev/null || echo CORE_STOPPED; "
        "printf 'SHELLCRASH_FIREWALL_REFS_AFTER_STOP='; "
        "iptables-save 2>/dev/null | grep -Eic 'shellcrash|clash|mihomo'",
        timeout=30,
        required=False,
    )
    stopped_count = firewall_count(gw)
    if "CORE_STOPPED" not in stopped or stopped_count is None or stopped_count != 0:
        rollback(gw, failsafe, "D01 init service did not stop cleanly")

    print("Testing start while the persistent autostart safety lock remains in place ...")
    run(gw, f"test -f {CRASHDIR}/.dis_startup && {INIT_PATH} test_start", timeout=60, required=False)

    core_ok = False
    rules_ok = False
    for _ in range(30):
        status, _ = run(gw, "pidof CrashCore 2>/dev/null", timeout=10, required=False)
        core_ok = bool(status.strip())
        if core_ok:
            count = firewall_count(gw)
            rules_ok = count is not None and count > 0
            if rules_ok:
                break
        time.sleep(2)
    if not core_ok or not rules_ok:
        rollback(gw, failsafe, "D01 init service did not restore both core and firewall rules")

    api, api_rc = run(
        gw,
        "code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "
        "http://127.0.0.1:9999/version 2>/dev/null); echo CONTROLLER_API_HTTP=$code; "
        "case \"$code\" in 401) exit 0;; *) exit 1;; esac",
        timeout=15,
        required=False,
    )
    if api_rc != 0 or "CONTROLLER_API_HTTP=401" not in api:
        rollback(gw, failsafe, "controller API did not require authentication (HTTP 401) after init start")

    session = requests.Session()
    session.trust_env = False
    dashboard_ok = False
    dashboard_marker, _ = run(
        gw,
        f"if test -s {CRASHDIR}/ui/index.html && "
        f"test -s {CRASHDIR}/ui/manifest.webmanifest && "
        f"test -n \"$(find {CRASHDIR}/ui/assets -type f -name '*.js' 2>/dev/null | head -n 1)\"; then "
        "echo DASHBOARD_COMPLETE; "
        f"elif test -e {CRASHDIR}/ui/index.html || "
        f"test -e {CRASHDIR}/ui/manifest.webmanifest || "
        f"test -n \"$(ls -A {CRASHDIR}/ui 2>/dev/null)\"; then echo DASHBOARD_PARTIAL; "
        "else echo DASHBOARD_NOT_INSTALLED; fi",
        timeout=10,
        required=False,
    )
    if "DASHBOARD_COMPLETE" in dashboard_marker:
        try:
            dashboard = session.get(DASHBOARD_URL, timeout=15, allow_redirects=True)
            print(f"DASHBOARD_HTTP_STATUS={dashboard.status_code}")
            dashboard_ok = dashboard.status_code == 200 and len(dashboard.content) > 100
        except requests.RequestException as error:
            print(f"DASHBOARD_CHECK_FAILED={type(error).__name__}")
        print(f"DASHBOARD_OPTIONAL_STATUS={'READY' if dashboard_ok else 'NOT_READY'}")
    elif "DASHBOARD_PARTIAL" in dashboard_marker:
        print("DASHBOARD_OPTIONAL_STATUS=PARTIAL")
    else:
        print("DASHBOARD_OPTIONAL_STATUS=NOT_INSTALLED")

    try:
        connectivity = session.get(
            "http://connectivitycheck.gstatic.com/generate_204",
            timeout=20,
            allow_redirects=False,
        )
        print(f"CLIENT_CONNECTIVITY_HTTP_STATUS={connectivity.status_code}")
        if connectivity.status_code != 204:
            rollback(gw, failsafe, "client connectivity failed after init start")
    except requests.RequestException as error:
        rollback(gw, failsafe, f"client connectivity failed: {type(error).__name__}")

    final_count = firewall_count(gw)
    final_state, final_rc = run(
        gw,
        f"test -f {CRASHDIR}/.dis_startup && pidof CrashCore >/dev/null 2>&1 && "
        "echo D01_AUTOSTART_STATE_OK",
        timeout=20,
        required=False,
    )
    if final_rc != 0 or "D01_AUTOSTART_STATE_OK" not in final_state or not final_count:
        rollback(gw, failsafe, "final autostart/core/rules state did not validate")
    if not failsafe.release(allow_mutated=True, require_armed=True):
        if failsafe.watchdog_completed or failsafe.watchdog_in_progress:
            print("BOOT_TEST_REPLACED_BY_ROUTER_WATCHDOG_ROLLBACK")
            raise SystemExit(2)
        rollback(gw, failsafe, "could not disarm boot failsafe safely")

    committed, committed_rc = run(
        gw,
        f"test -f {CRASHDIR}/.dis_startup && pidof CrashCore >/dev/null 2>&1 && "
        "rules=$(iptables-save 2>/dev/null) && "
        "refs=$(printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true) && "
        f"test \"${{refs:-0}}\" -gt 0 && test -x {INIT_PATH} && test -x {HOOK_PATH} && "
        "test -L /etc/rc.d/S95shellcrash_d01 && test -L /etc/rc.d/K10shellcrash_d01 && "
        f"test \"$(uci get firewall.ShellCrash.path 2>/dev/null)\" = \"{HOOK_PATH}\" && "
        f"rm -f {CRASHDIR}/.dis_startup && test ! -f {CRASHDIR}/.dis_startup && "
        "echo AUTOSTART_COMMIT_OK",
        timeout=20,
        required=False,
    )
    if committed_rc != 0 or "AUTOSTART_COMMIT_OK" not in committed:
        print("D01_BOOT_VALIDATED_BUT_AUTOSTART_COMMIT_FAILED")
        raise SystemExit(2)

    service_test_started = False
    print("D01_AUTOSTART_ENABLED_AND_VALIDATED")
    run(
        gw,
        "ls -l /etc/rc.d/S95shellcrash_d01 /etc/rc.d/K10shellcrash_d01; "
        "uci show firewall.ShellCrash; printf 'FINAL_SHELLCRASH_FIREWALL_REFS='; "
        "iptables-save 2>/dev/null | grep -Eic 'shellcrash|clash|mihomo'; df -h /data | tail -n 1",
        timeout=30,
        required=False,
    )
    if dashboard_ok:
        print(f"DASHBOARD_READY={DASHBOARD_URL}")
except SystemExit:
    raise
except Exception as error:
    if service_test_started:
        rollback(gw, failsafe, str(error) or type(error).__name__)
    if failsafe is not None and failsafe.reserved:
        if not failsafe.release(allow_mutated=False, require_armed=False):
            print("UNMUTATED_TRANSACTION_RETAINED_FOR_INSPECTION")
    print(f"D01_BOOT_INSTALL_FAILED_NO_ROUTING_CHANGES: {error}")
    print("AUTOSTART_SAFETY_LOCK_RETAINED")
    raise SystemExit(2)
