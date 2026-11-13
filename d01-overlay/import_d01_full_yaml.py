#!/usr/bin/env python3
"""Safely import a complete private Mihomo YAML for the D01 baseline."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import tempfile
from datetime import datetime

import gateway


CRASHDIR = "/data/ShellCrash"
YAMLDIR = f"{CRASHDIR}/yamls"
REMOTE_CANDIDATE = "/tmp/d01-public-config.candidate.yaml"
REMOTE_USER = "/tmp/d01-public-user.candidate.yaml"
REMOTE_DEFAULTS = "/tmp/d01-public-defaults.sh"
MAX_CONFIG_BYTES = 2 * 1024 * 1024


def run(gw, command: str, timeout: int = 30, required: bool = True):
    output = gw.run_cmd(command, die_on_error=False, timeout=timeout) or ""
    if output:
        print(output)
    if required and gw.errcode != 0:
        raise RuntimeError(f"router command failed (rc={gw.errcode})")
    return output, gw.errcode


def top_level_block(text: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}\s*:\s*(?:#.*)?$", text)
    if not match:
        return ""
    tail = text[match.end() :]
    next_key = re.search(r"(?m)^[A-Za-z0-9_-]+\s*:", tail)
    return tail[: next_key.start()] if next_key else tail


parser = argparse.ArgumentParser(
    description="Import a complete redir-host Mihomo YAML without starting ShellCrash"
)
parser.add_argument("file", help="private full Mihomo YAML; keep it outside the public repository")
args = parser.parse_args()

source_path = os.path.abspath(args.file)
if not os.path.isfile(source_path):
    raise SystemExit("ERROR: input YAML does not exist")
source_size = os.path.getsize(source_path)
if source_size < 100 or source_size > MAX_CONFIG_BYTES:
    raise SystemExit("ERROR: input YAML must be between 100 bytes and 2 MiB")

with open(source_path, "rb") as source_file:
    source_bytes = source_file.read()
try:
    source_text = source_bytes.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
except UnicodeDecodeError:
    raise SystemExit("ERROR: input YAML must be UTF-8") from None

for section in ("dns", "proxy-groups", "rules"):
    section_count = len(re.findall(rf"(?m)^{re.escape(section)}\s*:", source_text))
    if section_count != 1:
        raise SystemExit(f"ERROR: expected exactly one top-level {section} section")
proxy_counts = {
    section: len(re.findall(rf"(?m)^{re.escape(section)}\s*:", source_text))
    for section in ("proxies", "proxy-providers")
}
if any(count > 1 for count in proxy_counts.values()):
    raise SystemExit("ERROR: duplicate top-level proxies or proxy-providers section")
if not any(proxy_counts.values()):
    raise SystemExit("ERROR: missing top-level proxies or proxy-providers section")
if len(re.findall(r"(?m)^tun\s*:", source_text)) > 1:
    raise SystemExit("ERROR: duplicate top-level tun section")

dns_header = re.search(r"(?m)^dns\s*:(.*)$", source_text)
if not dns_header or dns_header.group(1).strip().split("#", 1)[0].strip():
    raise SystemExit("ERROR: dns must use a plain block mapping headed by 'dns:'")

dns_block = top_level_block(source_text, "dns")
if not re.search(r"(?m)^\s+enable\s*:\s*true\s*(?:#.*)?$", dns_block, re.I):
    raise SystemExit("ERROR: dns.enable must be true")
if not re.search(r"(?m)^\s+listen\s*:\s*['\"]?:1053['\"]?\s*(?:#.*)?$", dns_block):
    raise SystemExit("ERROR: dns.listen must be :1053")
if not re.search(r"(?m)^\s+enhanced-mode\s*:\s*redir-host\s*(?:#.*)?$", dns_block, re.I):
    raise SystemExit("ERROR: dns.enhanced-mode must be redir-host")
if not re.search(r"(?m)^\s+ipv6\s*:\s*false\s*(?:#.*)?$", dns_block, re.I):
    raise SystemExit("ERROR: dns.ipv6 must be false for the tested D01 baseline")
if re.search(r"(?m)^\s+(?:fake-ip-range|fake-ip-filter)\s*:", dns_block):
    raise SystemExit("ERROR: fake-ip fields are not allowed in the D01 UDP-direct baseline")

tun_block = top_level_block(source_text, "tun")
tun_header = re.search(r"(?m)^tun\s*:(.*)$", source_text)
if tun_header:
    tun_inline = tun_header.group(1).split("#", 1)[0].strip()
    if tun_inline and not re.fullmatch(
        r"\{\s*enable\s*:\s*false\s*\}", tun_inline, re.I
    ):
        raise SystemExit("ERROR: inline tun is accepted only as 'tun: {enable: false}'")
if tun_block and not re.search(
    r"(?m)^\s+enable\s*:\s*false\s*(?:#.*)?$", tun_block, re.I
):
    raise SystemExit("ERROR: TUN must be explicitly disabled on the tested D01 stock kernel")

source_hash = hashlib.sha256(source_bytes).hexdigest()
print(f"INPUT_SHA256={source_hash}")
print("INPUT_FULL_YAML_OK")

temp_path = None
user_temp_path = None
backup_dir = f"{YAMLDIR}/.d01-public-import-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
gw = gateway.Gateway()

try:
    with tempfile.NamedTemporaryFile(
        prefix="d01_full_yaml_", suffix=".yaml", delete=False, mode="w", encoding="utf-8", newline="\n"
    ) as temp_file:
        temp_path = temp_file.name
        temp_file.write(source_text.rstrip() + "\n")
    # ShellCrash 1.9.4 rebuilds the runtime from config.yaml plus user.yaml.
    # Keeping the complete DNS section in the user overlay prevents its
    # generator from replacing the requested redir-host policy with fake-ip.
    user_overlay = "dns:" + dns_block.rstrip() + "\n"
    with tempfile.NamedTemporaryFile(
        prefix="d01_user_yaml_", suffix=".yaml", delete=False, mode="w", encoding="utf-8", newline="\n"
    ) as user_temp_file:
        user_temp_path = user_temp_file.name
        user_temp_file.write(user_overlay)

    preflight, _ = run(
        gw,
        f"test -s {CRASHDIR}/menu.sh && test -x {CRASHDIR}/CrashCore.upx && "
        "test -z \"$(pidof CrashCore 2>/dev/null)\" && "
        "command -v iptables-save >/dev/null 2>&1 && rules=$(iptables-save 2>/dev/null) && "
        "refs=$(printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true) && "
        "test \"${refs:-0}\" -eq 0 && "
        f"mkdir -p {YAMLDIR} && touch {CRASHDIR}/.dis_startup && echo IMPORT_PREFLIGHT_OK",
        timeout=30,
    )
    if "IMPORT_PREFLIGHT_OK" not in preflight:
        raise RuntimeError("ShellCrash must be installed, stopped, and have no interception rules")

    if not gw.upload(temp_path, REMOTE_CANDIDATE):
        raise RuntimeError("cannot upload candidate YAML")
    if not gw.upload(user_temp_path, REMOTE_USER):
        raise RuntimeError("cannot upload ShellCrash DNS overlay")
    defaults_local = os.path.join("data", "payload_shellcrash", "d01_defaults.sh")
    if not gw.upload(defaults_local, REMOTE_DEFAULTS):
        raise RuntimeError("cannot upload D01 defaults")

    run(
        gw,
        f"tr -d '\\r' <{REMOTE_DEFAULTS} >{REMOTE_DEFAULTS}.lf && "
        f"mv -f {REMOTE_DEFAULTS}.lf {REMOTE_DEFAULTS} && chmod 0700 {REMOTE_DEFAULTS} && "
        f"chmod 0600 {REMOTE_CANDIDATE} {REMOTE_USER}",
    )

    candidate, candidate_rc = run(
        gw,
        f"{CRASHDIR}/CrashCore.upx -t -d {CRASHDIR} -f {REMOTE_CANDIDATE} "
        ">/tmp/d01-public-config-test.log 2>&1; rc=$?; "
        "tail -n 12 /tmp/d01-public-config-test.log; exit $rc",
        timeout=120,
        required=False,
    )
    if candidate_rc != 0:
        raise RuntimeError("Mihomo rejected the candidate YAML")
    print("CANDIDATE_VALID")

    install, install_rc = run(
        gw,
        f"mkdir {backup_dir} && chmod 0700 {backup_dir} && "
        f"if test -s {YAMLDIR}/config.yaml; then cp -f {YAMLDIR}/config.yaml {backup_dir}/config.yaml && "
        f"touch {backup_dir}/config.present; fi && "
        f"if test -s {YAMLDIR}/user.yaml; then cp -f {YAMLDIR}/user.yaml {backup_dir}/user.yaml && "
        f"touch {backup_dir}/user.present; fi && "
        f"sh {REMOTE_DEFAULTS} && rm -f {YAMLDIR}/.d01-config.new {YAMLDIR}/.d01-user.new && "
        f"cp -f {REMOTE_CANDIDATE} {YAMLDIR}/.d01-config.new && "
        f"cp -f {REMOTE_USER} {YAMLDIR}/.d01-user.new && "
        f"chmod 0600 {YAMLDIR}/.d01-config.new {YAMLDIR}/.d01-user.new && "
        f"mv -f {YAMLDIR}/.d01-config.new {YAMLDIR}/config.yaml && "
        f"mv -f {YAMLDIR}/.d01-user.new {YAMLDIR}/user.yaml && "
        f"{CRASHDIR}/CrashCore.upx -t -d {CRASHDIR} -f {YAMLDIR}/config.yaml "
        ">/tmp/d01-public-persistent-test.log 2>&1; rc=$?; "
        "tail -n 12 /tmp/d01-public-persistent-test.log; exit $rc",
        timeout=150,
        required=False,
    )
    if install_rc != 0:
        restored, restored_rc = run(
            gw,
            f"if test -f {backup_dir}/config.present; then "
            f"cp -f {backup_dir}/config.yaml {YAMLDIR}/config.yaml && chmod 0600 {YAMLDIR}/config.yaml; "
            f"else rm -f {YAMLDIR}/config.yaml; fi && "
            f"if test -f {backup_dir}/user.present; then "
            f"cp -f {backup_dir}/user.yaml {YAMLDIR}/user.yaml && chmod 0600 {YAMLDIR}/user.yaml; "
            f"else rm -f {YAMLDIR}/user.yaml; fi && "
            f"rm -f {YAMLDIR}/.d01-config.new {YAMLDIR}/.d01-user.new && "
            f"touch {CRASHDIR}/.dis_startup && test -f {CRASHDIR}/.dis_startup && "
            "echo PREVIOUS_PERSISTENT_CONFIG_RESTORED",
            required=False,
        )
        if restored_rc != 0 or "PREVIOUS_PERSISTENT_CONFIG_RESTORED" not in restored:
            raise RuntimeError(
                "persistent import failed and restoration could not be confirmed; autostart remains locked"
            )
        raise RuntimeError("persistent import failed; the prior config was restored when available")

    status, _ = run(
        gw,
        f"test -s {YAMLDIR}/config.yaml && test -s {YAMLDIR}/user.yaml && "
        f"grep -Eq '^[[:space:]]+enhanced-mode:[[:space:]]*redir-host' {YAMLDIR}/user.yaml && "
        f"grep -Eq \"^[[:space:]]+listen:[[:space:]]*['\\\"]?:1053['\\\"]?[[:space:]]*(#.*)?$\" "
        f"{YAMLDIR}/user.yaml && "
        f"test -f {CRASHDIR}/.dis_startup && "
        "test -z \"$(pidof CrashCore 2>/dev/null)\" && "
        "echo D01_CONFIG_IMPORTED_NOT_STARTED && echo SHELLCRASH_DNS_OVERLAY_READY && "
        "echo AUTOSTART_DISABLED_UNTIL_TESTED && "
        f"echo BACKUP_RETAINED={backup_dir} && df -h /data /tmp",
        timeout=30,
    )
    if "D01_CONFIG_IMPORTED_NOT_STARTED" not in status:
        raise RuntimeError("post-import state did not validate")
finally:
    run(
        gw,
        f"rm -f {REMOTE_CANDIDATE} {REMOTE_USER} {REMOTE_DEFAULTS} /tmp/d01-public-config-test.log "
        f"/tmp/d01-public-persistent-test.log {YAMLDIR}/.d01-config.new {YAMLDIR}/.d01-user.new",
        required=False,
    )
    if temp_path and os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass
    if user_temp_path and os.path.exists(user_temp_path):
        try:
            os.remove(user_temp_path)
        except OSError:
            pass
