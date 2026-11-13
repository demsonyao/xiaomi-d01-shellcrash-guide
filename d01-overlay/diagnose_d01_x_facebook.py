#!/usr/bin/env python3
"""Read-only diagnosis for domain-specific failures on the D01 Redir setup."""

import random
import socket
import struct
from urllib.parse import quote

import requests

import gateway


ROUTER = "192.168.31.1"
API = f"http://{ROUTER}:9999"
DOMAINS = ("x.com", "www.facebook.com", "www.instagram.com")


def run(gw, command, timeout=30):
    output = gw.run_cmd(command, die_on_error=False, timeout=timeout) or ""
    if output:
        print(output)
    return output, gw.errcode


def controller_secret(gw):
    output = gw.run_cmd(
        "sed -n 's/^secret=//p' /data/ShellCrash/configs/ShellCrash.cfg | head -n 1",
        die_on_error=False,
        timeout=10,
    ) or ""
    secret = output.strip()
    if len(secret) >= 2 and secret[0] == secret[-1] and secret[0] in {"'", '"'}:
        secret = secret[1:-1]
    return secret


def dns_query(domain, timeout=5):
    transaction = random.randint(0, 65535)
    header = struct.pack("!HHHHHH", transaction, 0x0100, 1, 0, 0, 0)
    labels = b"".join(bytes([len(part)]) + part.encode("ascii") for part in domain.split("."))
    packet = header + labels + b"\x00" + struct.pack("!HH", 1, 1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(packet, (ROUTER, 53))
        response, _ = sock.recvfrom(4096)
        if len(response) < 12:
            return "SHORT_RESPONSE"
        response_id, flags, _, answers, _, _ = struct.unpack("!HHHHHH", response[:12])
        if response_id != transaction:
            return "ID_MISMATCH"
        return f"RCODE={flags & 0xF},ANSWERS={answers}"
    except socket.timeout:
        return "TIMEOUT"
    except OSError as error:
        return f"SOCKET_ERROR={type(error).__name__}"
    finally:
        sock.close()


def web_probe(session, url):
    try:
        response = session.get(url, timeout=15, allow_redirects=False)
        return f"HTTP_{response.status_code}"
    except requests.exceptions.ConnectionError as error:
        detail = str(error).lower()
        if "name resolution" in detail or "getaddrinfo" in detail or "nameresolution" in detail:
            return "DNS_CONNECTION_ERROR"
        if "timed out" in detail:
            return "CONNECT_TIMEOUT"
        return "CONNECTION_ERROR"
    except requests.exceptions.Timeout:
        return "TIMEOUT"
    except requests.RequestException as error:
        return type(error).__name__.upper()


gw = gateway.Gateway()

print("=== D01_DOMAIN_FAILURE_PREFLIGHT ===")
run(
    gw,
    "printf 'CORE_PID='; pidof CrashCore 2>/dev/null || echo NONE; "
    "printf 'FIREWALL_REFS='; iptables-save 2>/dev/null | grep -Eic 'shellcrash|clash|mihomo'; "
    "grep -E '^(redir_mod|dns_mod|firewall_area|firewall_mod|ipv6_redir)=' "
    "/data/ShellCrash/configs/ShellCrash.cfg; "
    "sed -n '/^dns:/,/^[A-Za-z][A-Za-z0-9_-]*:/p' /tmp/ShellCrash/config.yaml | "
    "grep -E '^[[:space:]]+(listen|enhanced-mode|respect-rules|proxy-server-nameserver):'",
)

print("=== CLIENT_DNS_VIA_ROUTER ===")
for name in DOMAINS:
    print(f"DNS_{name.upper().replace('.', '_')}={dns_query(name)}")

session = requests.Session()
session.trust_env = False

print("=== CLIENT_TRANSPARENT_TCP_HTTPS ===")
for name in DOMAINS:
    result = web_probe(session, f"https://{name}/robots.txt")
    print(f"HTTPS_{name.upper().replace('.', '_')}={result}")

print("=== MIHOMO_DNS_API ===")
secret = controller_secret(gw)
headers = {"Authorization": f"Bearer {secret}"} if secret else {}
for name in DOMAINS:
    try:
        response = session.get(
            f"{API}/dns/query",
            headers=headers,
            params={"name": name, "type": "A"},
            timeout=12,
        )
        if response.status_code == 200:
            payload = response.json()
            answers = payload.get("Answer") or payload.get("answer") or []
            print(f"MIHOMO_DNS_{name.upper().replace('.', '_')}=HTTP_200,ANSWERS={len(answers)}")
        else:
            print(f"MIHOMO_DNS_{name.upper().replace('.', '_')}=HTTP_{response.status_code}")
    except (requests.RequestException, ValueError):
        print(f"MIHOMO_DNS_{name.upper().replace('.', '_')}=ERROR")

print("=== ROUTER_LOCAL_DOH_REACHABILITY ===")
run(
    gw,
    "for item in "
    "'CF|https://dns.cloudflare.com/dns-query?name=x.com&type=A' "
    "'ALI|https://dns.alidns.com/dns-query?name=x.com&type=A' "
    "'TENCENT|https://doh.pub/dns-query?name=x.com&type=A'; do "
    "tag=${item%%|*}; url=${item#*|}; "
    "code=$(curl -4 -sS -o /dev/null -w '%{http_code}' --max-time 10 "
    "-H 'accept: application/dns-json' \"$url\" 2>/dev/null); "
    "rc=$?; echo ${tag}_DOH_HTTP=${code:-000},RC=$rc; done",
    timeout=40,
)

print("=== ROUTER_EXPLICIT_MIHOMO_TCP ===")
run(
    gw,
    "for host in x.com www.facebook.com www.instagram.com; do "
    "code=$(curl -4 -x http://127.0.0.1:7890 -sS -o /dev/null -w '%{http_code}' "
    "--max-time 15 \"https://$host/robots.txt\" 2>/dev/null); "
    "rc=$?; key=$(echo $host | tr '.-' '__'); "
    "echo EXPLICIT_${key}_HTTP=${code:-000},RC=$rc; done",
    timeout=60,
)

print("DIAGNOSIS_COMPLETE_NO_CONFIG_CHANGES")
