#!/usr/bin/env python3
"""Read-only verification of the D01 TCP-Redir/redir-host installation."""

from __future__ import annotations

import re

import requests

import gateway


ROUTER = "192.168.31.1"
DASHBOARD = f"http://{ROUTER}:9999/ui/"


def run(gw, command: str, timeout: int = 30):
    output = gw.run_cmd(command, die_on_error=False, timeout=timeout) or ""
    if output:
        print(output)
    return output, gw.errcode


gw = gateway.Gateway()
output, rc = run(
    gw,
    "printf 'CORE_PID='; pidof CrashCore 2>/dev/null || echo NONE; "
    "code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 "
    "http://127.0.0.1:9999/version 2>/dev/null); echo CONTROLLER_API_HTTP=${code:-000}; "
    "printf 'FIREWALL_REFS='; iptables-save 2>/dev/null | grep -Eic 'shellcrash|clash|mihomo'; "
    "printf 'TCP_REDIR_RULES='; iptables-save -t nat 2>/dev/null | "
    "grep -Eic -- '-p tcp .*REDIRECT|^-A PREROUTING .* -j shellcrash'; "
    "printf 'TPROXY_RULES='; iptables-save 2>/dev/null | grep -c -- '-j TPROXY'; "
    "printf 'SHELLCRASH_MANGLE_REFS='; iptables-save -t mangle 2>/dev/null | "
    "grep -Eic 'shellcrash|clash|mihomo'; "
    "printf 'UDP_PROXY_PORT_RULES='; iptables-save 2>/dev/null | grep -Ei -- '-p udp' | "
    "grep -Ei -- 'TPROXY|REDIRECT|DNAT' | grep -Eic '789[0-5]'; "
    "printf 'TUN_DEVICE='; test -c /dev/net/tun && echo YES || echo NO; "
    "printf 'AUTOSTART_LOCK='; test -f /data/ShellCrash/.dis_startup && echo ON || echo OFF; "
    "grep -E '^(core_v|redir_mod|dns_mod|firewall_mod|firewall_area|ipv6_redir)=' "
    "/data/ShellCrash/configs/ShellCrash.cfg 2>/dev/null; "
    "printf 'REDIR_MODE_OK='; grep -q '^redir_mod=Redir' "
    "/data/ShellCrash/configs/ShellCrash.cfg 2>/dev/null && echo YES || echo NO; "
    "printf 'RUNTIME_DNS_MODE='; sed -n '/^dns:/,/^[A-Za-z][A-Za-z0-9_-]*:/p' "
    "/tmp/ShellCrash/config.yaml 2>/dev/null | sed -n 's/^[[:space:]]*enhanced-mode:[[:space:]]*//p' | head -n 1; "
    "printf 'RUNTIME_DNS_LISTEN='; sed -n '/^dns:/,/^[A-Za-z][A-Za-z0-9_-]*:/p' "
    "/tmp/ShellCrash/config.yaml 2>/dev/null | sed -n 's/^[[:space:]]*listen:[[:space:]]*//p' | head -n 1; "
    "printf 'RUNTIME_DNS_IPV6='; sed -n '/^dns:/,/^[A-Za-z][A-Za-z0-9_-]*:/p' "
    "/tmp/ShellCrash/config.yaml 2>/dev/null | sed -n 's/^[[:space:]]*ipv6:[[:space:]]*//p' | head -n 1; "
    "printf 'RUNTIME_TUN_ENABLED='; "
    "if sed -n '/^tun:/,/^[A-Za-z][A-Za-z0-9_-]*:/p' /tmp/ShellCrash/config.yaml 2>/dev/null | "
    "grep -Eqi '^tun:.*enable:[[:space:]]*true|^[[:space:]]+enable:[[:space:]]*true'; "
    "then echo YES; else echo NO; fi; "
    "printf 'RUNTIME_TUN_BASELINE='; "
    "if test \"$(grep -Ec '^tun:' /tmp/ShellCrash/config.yaml 2>/dev/null)\" -eq 1 && "
    "grep -Eq '^tun:[[:space:]]*\\{[[:space:]]*enable:[[:space:]]*false[[:space:]]*\\}[[:space:]]*$' "
    "/tmp/ShellCrash/config.yaml 2>/dev/null; then echo YES; else echo NO; fi; "
    "printf 'RUNTIME_CONFIG_MODE='; stat -c '%a' /tmp/ShellCrash/config.yaml 2>/dev/null; "
    "printf 'WAN_TCP_MANAGEMENT_BLOCK='; iptables -C INPUT -i eth0 -p tcp -m multiport "
    "--dports 22,80,443,7890,9999 -j REJECT >/dev/null 2>&1 && echo YES || echo NO; "
    "printf 'WAN_UDP_CONTROLLER_BLOCK='; iptables -C INPUT -i eth0 -p udp -m multiport "
    "--dports 7890,9999 -j REJECT >/dev/null 2>&1 && echo YES || echo NO; "
    "printf 'WAN6_TCP_MANAGEMENT_BLOCK='; ip6tables -C INPUT -i eth0 -p tcp -m multiport "
    "--dports 22,80,443,7890,9999 -j REJECT >/dev/null 2>&1 && echo YES || echo NO; "
    "printf 'WAN6_UDP_CONTROLLER_BLOCK='; ip6tables -C INPUT -i eth0 -p udp -m multiport "
    "--dports 7890,9999 -j REJECT >/dev/null 2>&1 && echo YES || echo NO; "
    "printf 'OTHER_PRIVATE_INPUT_ACCEPTS='; iptables-save -t filter 2>/dev/null | "
    "grep -E '^-A INPUT -s (10\\.|172\\.|192\\.168\\.)' | "
    "grep -v '192\\.168\\.31\\.0/24' | grep -c -- '-j ACCEPT'; true",
    timeout=40,
)

checks = {
    "core": bool(re.search(r"(?m)^CORE_PID=\d+$", output)),
    "api_auth": bool(re.search(r"(?m)^CONTROLLER_API_HTTP=401$", output)),
    "firewall": bool(re.search(r"(?m)^FIREWALL_REFS=([1-9]\d*)$", output)),
    "redir": bool(re.search(r"(?m)^TCP_REDIR_RULES=([1-9]\d*)$", output)),
    "no_tproxy": bool(re.search(r"(?m)^TPROXY_RULES=0$", output)),
    "no_mangle": bool(re.search(r"(?m)^SHELLCRASH_MANGLE_REFS=0$", output)),
    "no_udp_proxy_rules": bool(re.search(r"(?m)^UDP_PROXY_PORT_RULES=0$", output)),
    "no_tun_device": bool(re.search(r"(?m)^TUN_DEVICE=NO$", output)),
    "runtime_tun_off": bool(re.search(r"(?m)^RUNTIME_TUN_ENABLED=NO$", output)),
    "runtime_tun_baseline": bool(re.search(r"(?m)^RUNTIME_TUN_BASELINE=YES$", output)),
    "runtime_config_private": bool(re.search(r"(?m)^RUNTIME_CONFIG_MODE=600$", output)),
    "wan_tcp_block": bool(re.search(r"(?m)^WAN_TCP_MANAGEMENT_BLOCK=YES$", output)),
    "wan_udp_block": bool(re.search(r"(?m)^WAN_UDP_CONTROLLER_BLOCK=YES$", output)),
    "wan6_tcp_block": bool(re.search(r"(?m)^WAN6_TCP_MANAGEMENT_BLOCK=YES$", output)),
    "wan6_udp_block": bool(re.search(r"(?m)^WAN6_UDP_CONTROLLER_BLOCK=YES$", output)),
    "no_other_private_input": bool(re.search(r"(?m)^OTHER_PRIVATE_INPUT_ACCEPTS=0$", output)),
    "unlocked": bool(re.search(r"(?m)^AUTOSTART_LOCK=OFF$", output)),
    "redir_cfg": bool(re.search(r"(?m)^REDIR_MODE_OK=YES$", output)),
    "dns_cfg": bool(re.search(r"(?m)^dns_mod=redir_host$", output)),
    "dns_runtime": bool(re.search(r"(?m)^RUNTIME_DNS_MODE=redir-host$", output)),
    "dns_listen": bool(re.search(r"(?m)^RUNTIME_DNS_LISTEN=['\"]?:1053['\"]?$", output)),
    "dns_ipv6_off": bool(re.search(r"(?m)^RUNTIME_DNS_IPV6=false$", output)),
    "firewall_cfg": bool(re.search(r"(?m)^firewall_mod=iptables$", output)),
    "firewall_area": bool(re.search(r"(?m)^firewall_area=1$", output)),
    "ipv6_off": bool(re.search(r"(?m)^ipv6_redir=OFF$", output)),
}

session = requests.Session()
session.trust_env = False
dashboard_marker, _ = run(
    gw,
    "if test -s /data/ShellCrash/ui/index.html && "
    "test -s /data/ShellCrash/ui/manifest.webmanifest && "
    "test -n \"$(find /data/ShellCrash/ui/assets -type f -name '*.js' 2>/dev/null | head -n 1)\"; then "
    "echo DASHBOARD_COMPLETE; "
    "elif test -e /data/ShellCrash/ui/index.html || "
    "test -e /data/ShellCrash/ui/manifest.webmanifest || "
    "test -n \"$(ls -A /data/ShellCrash/ui 2>/dev/null)\"; then echo DASHBOARD_PARTIAL; "
    "else echo DASHBOARD_NOT_INSTALLED; fi",
    timeout=10,
)
dashboard_ok = False
if "DASHBOARD_COMPLETE" in dashboard_marker:
    try:
        response = session.get(DASHBOARD, timeout=12)
        print(f"DASHBOARD_HTTP_STATUS={response.status_code}")
        dashboard_ok = response.status_code == 200 and len(response.content) > 100
    except requests.RequestException as error:
        print(f"DASHBOARD_CHECK={type(error).__name__}")
    print(f"DASHBOARD_OPTIONAL_STATUS={'READY' if dashboard_ok else 'NOT_READY'}")
elif "DASHBOARD_PARTIAL" in dashboard_marker:
    print("DASHBOARD_OPTIONAL_STATUS=PARTIAL")
else:
    print("DASHBOARD_OPTIONAL_STATUS=NOT_INSTALLED")

try:
    response = session.get(
        "http://connectivitycheck.gstatic.com/generate_204",
        timeout=18,
        allow_redirects=False,
    )
    print(f"CLIENT_CONNECTIVITY_HTTP_STATUS={response.status_code}")
    checks["connectivity"] = response.status_code == 204
except requests.RequestException as error:
    print(f"CLIENT_CONNECTIVITY_CHECK={type(error).__name__}")
    checks["connectivity"] = False

failed = [name for name, passed in checks.items() if not passed]
if rc != 0 or failed:
    print("D01_VERIFY_FAILED=" + ",".join(failed or ["router_command"]))
    raise SystemExit(2)
print("CORE=RUNNING")
print("TCP_REDIR=YES")
print("DNS_MODE=redir_host")
print("DNS_LISTEN=:1053")
print("UDP_POLICY=DIRECT_VERIFIED")
print("D01_VERIFY_OK")
