#!/usr/bin/env python3
"""Enable D01 iptables interception with a router-side rollback guard."""

import os
import time

import requests

import gateway
from d01_failsafe import RouterFailsafe


CRASHDIR = "/data/ShellCrash"
REMOTE_FAILSAFE = "/tmp/d01_shellcrash_firewall_failsafe.sh"


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
    print(f"FIREWALL_TEST_FAILED: {reason}")
    print("Requesting the independent router watchdog to remove interception rules ...")
    if failsafe.request_rollback():
        print("ROUTER_WATCHDOG_ROLLBACK_COMPLETED")
    else:
        print("ROUTER_WATCHDOG_ROLLBACK_REQUIRES_INSPECTION")
    raise SystemExit(2)


gw = gateway.Gateway()
routing_mutation_started = False
failsafe = None

try:
    preflight, _ = run(
        gw,
        f"test -f {CRASHDIR}/.dis_startup && pidof CrashCore >/dev/null 2>&1 && "
        "command -v iptables-save >/dev/null 2>&1 && "
        "command -v iptables >/dev/null 2>&1 && command -v iptables-save >/dev/null 2>&1 && "
        "rules=$(iptables-save 2>/dev/null) && "
        "refs=$(printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true) && "
        "test \"${refs:-0}\" -eq 0 && echo FIREWALL_PREFLIGHT_OK",
    )
    if "FIREWALL_PREFLIGHT_OK" not in preflight:
        raise RuntimeError("core, safety lock, clean rule state, or iptables preflight failed")
    failsafe = RouterFailsafe(
        lambda command, timeout=30, required=True: run(
            gw, command, timeout=timeout, required=required
        ),
        REMOTE_FAILSAFE,
        "firewall-test",
        "/tmp/shellcrash_firewall_failsafe.out",
        "FIREWALL_FAILSAFE_ARMED_180_SECONDS",
    )
    failsafe.reserve()
    recheck, _ = run(
        gw,
        f"test -f {CRASHDIR}/.dis_startup && pidof CrashCore >/dev/null 2>&1 && "
        "rules=$(iptables-save 2>/dev/null) && "
        "refs=$(printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true) && "
        "test \"${refs:-0}\" -eq 0 && echo RESERVED_PREFLIGHT_OK",
    )
    if "RESERVED_PREFLIGHT_OK" not in recheck:
        raise RuntimeError("router state changed while reserving the firewall transaction")

    failsafe_local = os.path.join("data", "payload_shellcrash", "d01_firewall_failsafe.sh")
    if not gw.upload(failsafe_local, REMOTE_FAILSAFE):
        raise RuntimeError("cannot upload firewall failsafe")
    run(
        gw,
        f"tr -d '\\r' < {REMOTE_FAILSAFE} > {REMOTE_FAILSAFE}.lf && "
        f"mv -f {REMOTE_FAILSAFE}.lf {REMOTE_FAILSAFE} && chmod 0700 {REMOTE_FAILSAFE} && "
        f"sh -n {REMOTE_FAILSAFE} && echo FIREWALL_FAILSAFE_SCRIPT_VALID",
    )

    if not failsafe.arm():
        if not failsafe.release(allow_mutated=False, require_armed=False):
            print("UNMUTATED_TRANSACTION_RETAINED_FOR_INSPECTION")
        raise RuntimeError("could not arm and verify the firewall failsafe")
    if not failsafe.mark_mutation():
        if not failsafe.release(allow_mutated=False, require_armed=True):
            print("UNMUTATED_TRANSACTION_RETAINED_FOR_INSPECTION")
        raise RuntimeError("could not authorize the firewall mutation")
    routing_mutation_started = True

    print("Selecting the D01-compatible iptables backend ...")
    run(
        gw,
        f"CRASHDIR={CRASHDIR}; . {CRASHDIR}/libs/set_config.sh; "
        "setconfig firewall_mod iptables; "
        f"touch {CRASHDIR}/.dis_startup; grep '^firewall_mod=' {CRASHDIR}/configs/ShellCrash.cfg",
    )

    print("Applying ShellCrash LAN interception rules ...")
    _, apply_rc = run(
        gw,
        f"CRASHDIR={CRASHDIR}; export CRASHDIR; . {CRASHDIR}/libs/get_config.sh; "
        f". {CRASHDIR}/starts/fw_start.sh >/tmp/shellcrash_fw_start.stdout "
        "2>/tmp/shellcrash_fw_start.stderr; rc=$?; echo FIREWALL_START_RC=$rc; exit 0",
        timeout=90,
        required=False,
    )
    rule_count = None
    for _ in range(15):
        rule_count = firewall_count(gw)
        if rule_count and rule_count > 0:
            break
        time.sleep(1)
    print(f"SHELLCRASH_FIREWALL_REFS={rule_count if rule_count is not None else 'UNKNOWN'}")
    if not rule_count:
        run(
            gw,
            "tail -n 100 /tmp/shellcrash_fw_start.stderr /tmp/shellcrash_fw_start.stdout "
            f"/tmp/ShellCrash/ShellCrash.log 2>/dev/null; "
            f"grep -E '^(firewall_mod|firewall_area|redir_mod|dns_mod)=' {CRASHDIR}/configs/ShellCrash.cfg",
            timeout=20,
            required=False,
        )
        rollback(gw, failsafe, f"iptables rules were not created (fw_start rc={apply_rc})")

    session = requests.Session()
    session.trust_env = False
    internet_ok = False
    for attempt in range(1, 5):
        try:
            response = session.get(
                "http://connectivitycheck.gstatic.com/generate_204",
                timeout=15,
                allow_redirects=False,
            )
            print(f"CLIENT_CONNECTIVITY_ATTEMPT_{attempt}_HTTP_STATUS={response.status_code}")
            internet_ok = response.status_code == 204
        except requests.RequestException as error:
            print(f"CLIENT_CONNECTIVITY_ATTEMPT_{attempt}={type(error).__name__}")
        if internet_ok:
            break
        time.sleep(3)
    if not internet_ok:
        rollback(gw, failsafe, "client Internet connectivity failed after enabling interception")

    final_count = firewall_count(gw)
    state, state_rc = run(
        gw,
        f"test -f {CRASHDIR}/.dis_startup && pidof CrashCore >/dev/null 2>&1 && "
        "echo TRANSPARENT_PROXY_STATE_OK",
        timeout=20,
        required=False,
    )
    if state_rc != 0 or "TRANSPARENT_PROXY_STATE_OK" not in state or not final_count:
        rollback(gw, failsafe, "final core, rules, or safety-lock state did not validate")
    if not failsafe.release(allow_mutated=True, require_armed=True):
        if failsafe.watchdog_completed or failsafe.watchdog_in_progress:
            print("FIREWALL_TEST_REPLACED_BY_ROUTER_WATCHDOG_ROLLBACK")
            raise SystemExit(2)
        rollback(gw, failsafe, "could not disarm the firewall failsafe safely")

    routing_mutation_started = False
    print("TRANSPARENT_PROXY_OK_AUTOSTART_STILL_DISABLED")
except SystemExit:
    raise
except Exception as error:
    if routing_mutation_started:
        rollback(gw, failsafe, str(error) or type(error).__name__)
    if failsafe is not None and failsafe.reserved:
        if not failsafe.release(allow_mutated=False, require_armed=False):
            print("UNMUTATED_TRANSACTION_RETAINED_FOR_INSPECTION")
    print(f"FIREWALL_PRECHECK_FAILED_NO_ROUTING_CHANGES: {error}")
    raise SystemExit(2)
