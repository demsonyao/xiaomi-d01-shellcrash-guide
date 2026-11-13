#!/usr/bin/env python3
"""Safely probe TPROXY in a unique, unhooked temporary mangle chain."""

import secrets

import gateway


TOKEN = secrets.token_hex(4).upper()
CHAIN = f"D01TPX_{TOKEN}"
MARKER = f"/tmp/{CHAIN}.created"
PROBE_LOG = f"/tmp/{CHAIN}.log"


def run(gw, command, timeout=20, required=False):
    output = gw.run_cmd(command, die_on_error=False, timeout=timeout) or ""
    if output:
        print(output)
    if required and gw.errcode != 0:
        raise RuntimeError(f"Router command failed (rc={gw.errcode})")
    return output, gw.errcode


gw = gateway.Gateway()


def cleanup(gw):
    return run(
        gw,
        f"if test \"$(cat {MARKER} 2>/dev/null)\" = \"{CHAIN}\"; then "
        f"iptables -t mangle -F {CHAIN} 2>/dev/null; "
        f"iptables -t mangle -X {CHAIN} 2>/dev/null; fi; "
        f"rm -f {MARKER} {PROBE_LOG}",
        required=False,
    )

try:
    print("=== D01_TPROXY_EXACT_PROBE ===")
    run(
        gw,
        "printf 'KERNEL='; uname -r; "
        "test -c /dev/net/tun && echo TUN_DEVICE=YES || echo TUN_DEVICE=NO; "
        "printf 'TPROXY_HELP='; "
        "iptables -j TPROXY -h 2>&1 | grep -q -- '--on-port' && echo YES || echo NO; "
        "printf 'TPROXY_REGISTERED='; "
        "grep -qw TPROXY /proc/net/ip_tables_targets 2>/dev/null && echo YES || echo NO; "
        "printf 'TPROXY_MODULE_FILES='; "
        "find /lib/modules -type f 2>/dev/null | grep -Eic '/(xt_TPROXY|ipt_TPROXY)\\.ko'; "
        "printf 'MODPROBE='; command -v modprobe >/dev/null 2>&1 && echo YES || echo NO",
        required=True,
    )

    probe_command = (
        f"rm -f {MARKER} {PROBE_LOG}; "
        f"if iptables -t mangle -S {CHAIN} >/dev/null 2>&1; then "
        "echo PROBE_CHAIN_COLLISION; exit 11; fi; "
        f"iptables -t mangle -N {CHAIN} >{PROBE_LOG} 2>&1 || exit 10; "
        f"echo {CHAIN} >{MARKER}; echo PROBE_CHAIN_CREATED={CHAIN}; "
        f"iptables -t mangle -A {CHAIN} -p udp -j TPROXY "
        f"--on-port 7895 --tproxy-mark 1/1 >>{PROBE_LOG} 2>&1; "
        "rc=$?; "
        f"iptables -t mangle -S {CHAIN} 2>/dev/null; "
        f"iptables -t mangle -F {CHAIN} 2>/dev/null; "
        f"iptables -t mangle -X {CHAIN} 2>/dev/null; cleanup_rc=$?; "
        "echo RULE_INSERT_RC=$rc; "
        f"cat {PROBE_LOG} 2>/dev/null; "
        f"rm -f {MARKER} {PROBE_LOG}; "
        "test $cleanup_rc -eq 0 && echo PROBE_CHAIN_REMOVED; "
        "exit 0"
    )
    output, _ = run(gw, probe_command, timeout=30)
    if "PROBE_CHAIN_CREATED=" not in output:
        raise RuntimeError("could not create a unique probe chain")
    if "PROBE_CHAIN_REMOVED" not in output:
        raise RuntimeError("temporary probe chain cleanup was not confirmed")

    if "RULE_INSERT_RC=0" in output and "--on-port 7895" in output:
        print("TPROXY_KERNEL_RULE_TEST=SUPPORTED")
    else:
        print("TPROXY_KERNEL_RULE_TEST=UNSUPPORTED")
    print("PROBE_CHAIN_REMOVED_NO_TRAFFIC_HOOKS_CHANGED")
except Exception as error:
    cleanup(gw)
    print(f"TPROXY_PROBE_FAILED: {error}")
    raise SystemExit(2)
