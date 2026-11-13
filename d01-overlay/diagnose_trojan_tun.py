#!/usr/bin/env python3
"""Read-only D01 TUN capability and per-protocol Mihomo delay diagnosis."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from statistics import median
from urllib.parse import quote

import requests

import gateway


CRASHDIR = "/data/ShellCrash"
API = "http://192.168.31.1:9999"
TEST_URL = "http://www.gstatic.com/generate_204"

session = requests.Session()
# Never send router API requests through a Windows/system HTTP proxy.
session.trust_env = False


def sanitized_detail(response, node_name):
    try:
        payload = response.json()
        if isinstance(payload, dict):
            raw = str(payload.get("message") or payload.get("error") or payload)
        else:
            raw = str(payload)
    except ValueError:
        raw = response.text or "EMPTY_BODY"
    if node_name:
        raw = raw.replace(node_name, "<node>")
    raw = re.sub(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}", "<uuid>", raw)
    raw = re.sub(r"(?<![A-Za-z0-9])(?:\d{1,3}\.){3}\d{1,3}(?![A-Za-z0-9])", "<ip>", raw)
    raw = re.sub(r"(?i)\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", "<host>", raw)
    raw = re.sub(r":\d{2,5}\b", ":<port>", raw)
    raw = re.sub(r"\b[A-Za-z0-9_+/=-]{18,}\b", "<token>", raw)
    raw = " ".join(raw.split())
    return raw[:240] or "EMPTY_BODY"


def classify_response(response, node_name):
    if response.status_code == 200:
        try:
            delay = int(response.json().get("delay", 0))
        except (TypeError, ValueError, requests.JSONDecodeError):
            delay = 0
        return ("OK" if delay > 0 else "ZERO_DELAY", delay, "")

    message = sanitized_detail(response, node_name)
    lowered = message.lower()
    if "timeout" in lowered or "deadline" in lowered:
        category = "TIMEOUT"
    elif "resolve" in lowered or "dns" in lowered or "no such host" in lowered:
        category = "DNS_ERROR"
    elif "tls" in lowered or "certificate" in lowered or "handshake" in lowered:
        category = "TLS_ERROR"
    elif "refused" in lowered:
        category = "CONNECTION_REFUSED"
    elif "network is unreachable" in lowered or "no route" in lowered:
        category = "NETWORK_UNREACHABLE"
    else:
        category = f"HTTP_{response.status_code}"
    return category, 0, message


gw = gateway.Gateway()

print("\n=== D01_TUN_TPROXY_CAPABILITY ===")
capability = gw.run_cmd(
    "printf 'KERNEL='; uname -r; "
    "test -c /dev/net/tun && echo TUN_DEVICE=YES || echo TUN_DEVICE=NO; "
    "grep -qw tun /proc/modules 2>/dev/null && echo TUN_MODULE_LOADED=YES || echo TUN_MODULE_LOADED=NO; "
    "printf 'TUN_MODULE_FILE_COUNT='; find /lib/modules/$(uname -r) -name 'tun.ko*' 2>/dev/null | wc -l; "
    f"test -s {CRASHDIR}/tools/tun.ko && echo SHELLCRASH_TUN_KO=YES || echo SHELLCRASH_TUN_KO=NO; "
    "grep -qw TPROXY /proc/net/ip_tables_targets 2>/dev/null && echo TPROXY_KERNEL_TARGET=YES || echo TPROXY_KERNEL_TARGET=NO; "
    "command -v modprobe >/dev/null 2>&1 && echo MODPROBE=YES || echo MODPROBE=NO; "
    f"grep -E '^(redir_mod|firewall_mod|firewall_area|dns_mod|ipv6_redir)=' {CRASHDIR}/configs/ShellCrash.cfg; "
    "grep -E '^tun:' /tmp/ShellCrash/config.yaml 2>/dev/null | head -n 1",
    die_on_error=False,
    timeout=30,
)
print(capability or "")

# Read the controller secret into process memory only. Never print it.
secret_output = gw.run_cmd(
    f"sed -n 's/^secret=//p' {CRASHDIR}/configs/ShellCrash.cfg | head -n 1",
    die_on_error=False,
    timeout=10,
)
if gw.errcode != 0:
    raise SystemExit("ERROR: Cannot read controller authentication metadata")
secret = (secret_output or "").strip()
if len(secret) >= 2 and secret[0] == secret[-1] and secret[0] in {"'", '"'}:
    secret = secret[1:-1]
headers = {"Authorization": f"Bearer {secret}"} if secret else {}

try:
    proxy_response = session.get(f"{API}/proxies", headers=headers, timeout=15)
    proxy_response.raise_for_status()
    proxy_map = proxy_response.json().get("proxies", {})
except requests.HTTPError as error:
    status = error.response.status_code if error.response is not None else "unknown"
    raise SystemExit(f"ERROR: Cannot query Mihomo proxy API (HTTP {status})") from None
except (requests.RequestException, ValueError) as error:
    raise SystemExit(f"ERROR: Cannot query Mihomo proxy API ({type(error).__name__})") from None

targets = []
for name, details in proxy_map.items():
    proxy_type = str(details.get("type", "")).lower()
    if proxy_type == "trojan":
        targets.append(("TROJAN", name))
    elif proxy_type == "vless":
        targets.append(("VLESS", name))

if not any(protocol == "TROJAN" for protocol, _ in targets):
    raise SystemExit("ERROR: No Trojan nodes were returned by the active Mihomo API")


def test_node(protocol, name):
    try:
        response = session.get(
            f"{API}/proxies/{quote(name, safe='')}/delay",
            headers=headers,
            params={"url": TEST_URL, "timeout": 7000, "expected": "204"},
            timeout=12,
        )
        category, delay, detail = classify_response(response, name)
    except requests.Timeout:
        category, delay, detail = "API_REQUEST_TIMEOUT", 0, "local API request timed out"
    except requests.RequestException:
        category, delay, detail = "API_REQUEST_ERROR", 0, "local API request failed"
    return protocol, category, delay, detail


print("=== MIHOMO_PROTOCOL_DELAY_TEST ===")
print(f"TESTING_TROJAN={sum(protocol == 'TROJAN' for protocol, _ in targets)}")
print(f"TESTING_VLESS={sum(protocol == 'VLESS' for protocol, _ in targets)}")

results = []
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [executor.submit(test_node, protocol, name) for protocol, name in targets]
    for future in as_completed(futures):
        results.append(future.result())

for protocol in ("TROJAN", "VLESS"):
    protocol_results = [
        (category, delay, detail)
        for item_protocol, category, delay, detail in results
        if item_protocol == protocol
    ]
    categories = Counter(category for category, _, _ in protocol_results)
    details = Counter(detail for category, _, detail in protocol_results if category != "OK" and detail)
    delays = [delay for category, delay, _ in protocol_results if category == "OK" and delay > 0]
    print(f"{protocol}_TOTAL={len(protocol_results)}")
    print(f"{protocol}_RESULTS=" + ",".join(f"{key}:{value}" for key, value in sorted(categories.items())))
    for index, (detail, count) in enumerate(details.most_common(5), 1):
        print(f"{protocol}_ERROR_DETAIL_{index}_COUNT={count}")
        print(f"{protocol}_ERROR_DETAIL_{index}={detail}")
    if delays:
        print(f"{protocol}_MEDIAN_DELAY_MS={int(median(delays))}")

print("DIAGNOSIS_COMPLETE_NO_CONFIG_CHANGES")
