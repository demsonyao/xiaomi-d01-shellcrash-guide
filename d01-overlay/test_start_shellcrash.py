#!/usr/bin/env python3
"""Start ShellCrash once with an automatic rollback and connectivity checks."""

import os
import time

import requests

import gateway
from d01_failsafe import RouterFailsafe


CRASHDIR = "/data/ShellCrash"
REMOTE_FAILSAFE = "/tmp/d01_shellcrash_test_failsafe.sh"
DASHBOARD_URL = "http://192.168.31.1:9999/ui/"


def router_command(gw, command, timeout=30, required=True):
    output = gw.run_cmd(command, die_on_error=False, timeout=timeout) or ""
    if output:
        print(output)
    if required and gw.errcode != 0:
        raise RuntimeError(f"Router command failed (rc={gw.errcode})")
    return output, gw.errcode


def rollback(gw, failsafe, reason):
    print(f"CONTROLLED_START_FAILED: {reason}")
    print("Requesting the independent router watchdog to restore direct routing ...")
    if failsafe.request_rollback():
        print("ROUTER_WATCHDOG_ROLLBACK_COMPLETED")
    else:
        print("ROUTER_WATCHDOG_ROLLBACK_REQUIRES_INSPECTION")
    raise SystemExit(2)


gw = gateway.Gateway()
routing_mutation_started = False
failsafe = None

try:
    preflight, _ = router_command(
        gw,
        f"test -f {CRASHDIR}/.dis_startup && "
        f"test -s {CRASHDIR}/yamls/config.yaml && "
        f"test -x {CRASHDIR}/CrashCore.upx && "
        "test -s /tmp/ShellCrash/config.yaml && test -x /tmp/ShellCrash/CrashCore && "
        "! pidof CrashCore >/dev/null 2>&1 && command -v iptables-save >/dev/null 2>&1 && "
        "rules=$(iptables-save 2>/dev/null) && "
        "refs=$(printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true) && "
        "test \"${refs:-0}\" -eq 0 && echo PREFLIGHT_OK",
    )
    if "PREFLIGHT_OK" not in preflight:
        raise RuntimeError("preflight safety checks did not pass")
    print("Validating the prepared runtime configuration before starting ...")
    _, validation_rc = router_command(
        gw,
        f"{CRASHDIR}/CrashCore.upx -t -d {CRASHDIR} "
        "-f /tmp/ShellCrash/config.yaml 2>&1; rc=$?; exit $rc",
        timeout=60,
        required=False,
    )
    if validation_rc != 0:
        raise RuntimeError("prepared runtime configuration was rejected by Mihomo")

    failsafe = RouterFailsafe(
        lambda command, timeout=30, required=True: router_command(
            gw, command, timeout=timeout, required=required
        ),
        REMOTE_FAILSAFE,
        "controlled-start",
        "/tmp/shellcrash_failsafe.log",
        "FAILSAFE_ARMED_180_SECONDS",
    )
    failsafe.reserve()

    # The shared reservation closes the concurrency window; recheck the state
    # before uploading or arming anything.
    recheck, _ = router_command(
        gw,
        f"test -f {CRASHDIR}/.dis_startup && ! pidof CrashCore >/dev/null 2>&1 && "
        "command -v iptables-save >/dev/null 2>&1 && "
        "rules=$(iptables-save 2>/dev/null) && "
        "refs=$(printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true) && "
        "test \"${refs:-0}\" -eq 0 && echo RESERVED_PREFLIGHT_OK",
    )
    if "RESERVED_PREFLIGHT_OK" not in recheck:
        raise RuntimeError("router state changed while reserving the controlled-start transaction")

    failsafe_local = os.path.join("data", "payload_shellcrash", "d01_test_failsafe.sh")
    if not gw.upload(failsafe_local, REMOTE_FAILSAFE):
        raise RuntimeError("cannot upload the router-side failsafe")
    router_command(
        gw,
        f"tr -d '\\r' < {REMOTE_FAILSAFE} > {REMOTE_FAILSAFE}.lf && "
        f"mv -f {REMOTE_FAILSAFE}.lf {REMOTE_FAILSAFE} && chmod 0700 {REMOTE_FAILSAFE} && "
        f"sh -n {REMOTE_FAILSAFE} && echo FAILSAFE_SCRIPT_VALID",
    )

    if not failsafe.arm():
        if not failsafe.release(allow_mutated=False, require_armed=False):
            print("UNMUTATED_TRANSACTION_RETAINED_FOR_INSPECTION")
        raise RuntimeError("could not arm and verify the router-side failsafe")
    if not failsafe.mark_mutation():
        if not failsafe.release(allow_mutated=False, require_armed=True):
            print("UNMUTATED_TRANSACTION_RETAINED_FOR_INSPECTION")
        raise RuntimeError("could not authorize the controlled-start mutation")
    routing_mutation_started = True

    print("Starting the prepared Mihomo runtime in controlled test mode ...")
    _, start_rc = router_command(
        gw,
        f"rm -f {CRASHDIR}/.start_error; CRASHDIR={CRASHDIR}; export CRASHDIR; "
        f". {CRASHDIR}/libs/get_config.sh; . {CRASHDIR}/starts/start_legacy.sh; "
        "start_legacy \"$COMMAND\" shellcrash; echo PREPARED_CORE_LAUNCH_ISSUED",
        timeout=45,
        required=False,
    )
    if start_rc != 0:
        rollback(gw, failsafe, f"start command returned {start_rc}")

    core_running = False
    for _ in range(20):
        status, _ = router_command(gw, "pidof CrashCore 2>/dev/null", timeout=10, required=False)
        if status.strip():
            core_running = True
            break
        time.sleep(2)
    if not core_running:
        router_command(
            gw,
            "tail -n 100 /tmp/ShellCrash/core_test.log /tmp/ShellCrash/debug.log "
            "/tmp/ShellCrash/ShellCrash.log 2>/dev/null",
            timeout=20,
            required=False,
        )
        rollback(gw, failsafe, "Mihomo core did not remain running")

    generated, generated_rc = router_command(
        gw,
        "test -s /tmp/ShellCrash/config.yaml && echo RUNTIME_CONFIG_PRESENT",
        timeout=20,
        required=False,
    )
    if generated_rc != 0 or "RUNTIME_CONFIG_PRESENT" not in generated:
        rollback(gw, failsafe, "ShellCrash runtime configuration disappeared during startup")

    api_check, api_rc = router_command(
        gw,
        "count=0; code=000; while [ $count -lt 20 ]; do "
        "code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "
        "http://127.0.0.1:9999/version 2>/dev/null); "
        "case \"$code\" in 401) echo CONTROLLER_API_HTTP=$code; exit 0;; esac; "
        "count=$((count + 1)); sleep 1; done; echo CONTROLLER_API_LAST_HTTP=$code; exit 1",
        timeout=45,
        required=False,
    )
    if api_rc != 0 or "CONTROLLER_API_HTTP=401" not in api_check:
        router_command(
            gw,
            "grep -E '^(external-controller|external-ui|secret):' /tmp/ShellCrash/config.yaml 2>/dev/null "
            "| sed 's/^secret:.*/secret: <configured>/'; netstat -lnt 2>/dev/null | grep ':9999' || true",
            timeout=20,
            required=False,
        )
        rollback(gw, failsafe, "Mihomo controller API is unavailable or has no authentication")

    router_command(
        gw,
        "printf 'SHELLCRASH_FIREWALL_REFS='; iptables-save 2>/dev/null | "
        "grep -Eic 'shellcrash|clash|mihomo'; printf 'DATA_USAGE='; df -h /data | tail -n 1",
        timeout=20,
        required=False,
    )

    session = requests.Session()
    session.trust_env = False
    dashboard_ok = False
    dashboard_marker, _ = router_command(
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
            dashboard_response = session.get(DASHBOARD_URL, timeout=15, allow_redirects=True)
            dashboard_ok = dashboard_response.status_code == 200 and len(dashboard_response.content) > 100
            print(f"DASHBOARD_HTTP_STATUS={dashboard_response.status_code}")
        except requests.RequestException as error:
            print(f"DASHBOARD_CHECK_FAILED={type(error).__name__}")
        print(f"DASHBOARD_OPTIONAL_STATUS={'READY' if dashboard_ok else 'NOT_READY'}")
    elif "DASHBOARD_PARTIAL" in dashboard_marker:
        print("DASHBOARD_OPTIONAL_STATUS=PARTIAL")
    else:
        print("DASHBOARD_OPTIONAL_STATUS=NOT_INSTALLED")

    internet_ok = False
    for url in ("http://connectivitycheck.gstatic.com/generate_204", "http://www.baidu.com/"):
        try:
            response = session.get(url, timeout=15, allow_redirects=True)
            print(f"CLIENT_CONNECTIVITY_HTTP_STATUS={response.status_code}")
            if response.status_code < 500:
                internet_ok = True
                break
        except requests.RequestException as error:
            print(f"CLIENT_CONNECTIVITY_CHECK={type(error).__name__}")
    if not internet_ok:
        rollback(gw, failsafe, "client Internet connectivity check failed")

    success, success_rc = router_command(
        gw,
        f"touch {CRASHDIR}/.dis_startup && test -f {CRASHDIR}/.dis_startup && "
        "pidof CrashCore >/dev/null 2>&1 && rules=$(iptables-save 2>/dev/null) && "
        "refs=$(printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true) && "
        "test \"${refs:-0}\" -eq 0 && echo CONTROLLED_START_STATE_OK",
        timeout=20,
        required=False,
    )
    if success_rc != 0 or "CONTROLLED_START_STATE_OK" not in success:
        rollback(gw, failsafe, "final controlled-start state did not validate")
    if not failsafe.release(allow_mutated=True, require_armed=True):
        if failsafe.watchdog_completed or failsafe.watchdog_in_progress:
            print("CONTROLLED_START_REPLACED_BY_ROUTER_WATCHDOG_ROLLBACK")
            raise SystemExit(2)
        rollback(gw, failsafe, "could not disarm the failsafe safely")

    routing_mutation_started = False
    print("CONTROLLED_START_OK_AUTOSTART_STILL_DISABLED")
    if dashboard_ok:
        print(f"DASHBOARD_READY={DASHBOARD_URL}")
except SystemExit:
    raise
except Exception as error:
    if routing_mutation_started:
        rollback(gw, failsafe, str(error) or type(error).__name__)
    if failsafe is not None and failsafe.reserved:
        if not failsafe.release(allow_mutated=False, require_armed=False):
            print("UNMUTATED_TRANSACTION_RETAINED_FOR_INSPECTION")
    print(f"CONTROLLED_START_PRECHECK_FAILED_NO_ROUTING_CHANGES: {error}")
    raise SystemExit(2)
