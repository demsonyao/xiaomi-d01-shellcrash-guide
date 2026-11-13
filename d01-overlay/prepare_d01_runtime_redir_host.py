#!/usr/bin/env python3
"""Build and validate the D01 redir-host runtime while traffic stays direct."""

from __future__ import annotations

import getpass
import os
import re
import tempfile

import gateway


CRASHDIR = "/data/ShellCrash"
TMPDIR = "/tmp/ShellCrash"
REMOTE_SECRET = "/tmp/.d01_controller_secret"


def run(gw, command: str, timeout: int = 30, required: bool = True):
    output = gw.run_cmd(command, die_on_error=False, timeout=timeout) or ""
    if output:
        print(output)
    if required and gw.errcode != 0:
        raise RuntimeError(f"router command failed (rc={gw.errcode})")
    return output, gw.errcode


gw = gateway.Gateway()
secret_temp = None

try:
    preflight, _ = run(
        gw,
        f"test -f {CRASHDIR}/.dis_startup && test -s {CRASHDIR}/yamls/config.yaml && "
        f"test -s {CRASHDIR}/yamls/user.yaml && "
        f"grep -Eq '^[[:space:]]+enhanced-mode:[[:space:]]*redir-host' {CRASHDIR}/yamls/user.yaml && "
        f"grep -Eq \"^[[:space:]]+listen:[[:space:]]*['\\\"]?:1053['\\\"]?[[:space:]]*(#.*)?$\" "
        f"{CRASHDIR}/yamls/user.yaml && "
        f"test -x {CRASHDIR}/CrashCore.upx && test -z \"$(pidof CrashCore 2>/dev/null)\" && "
        "command -v iptables-save >/dev/null 2>&1 && rules=$(iptables-save 2>/dev/null) && "
        "refs=$(printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true) && "
        "test \"${refs:-0}\" -eq 0 && "
        f"grep -q '^dns_mod=redir_host$' {CRASHDIR}/configs/ShellCrash.cfg && "
        "echo PREPARE_PREFLIGHT_OK",
        timeout=35,
    )
    if "PREPARE_PREFLIGHT_OK" not in preflight:
        raise RuntimeError("expected a stopped, direct-routing redir-host install with the safety lock")

    stale, _ = run(
        gw,
        "ps w 2>/dev/null | grep -E '/data/ShellCrash/(start.sh start|starts/bfstart.sh)' | grep -v grep",
        timeout=15,
        required=False,
    )
    if stale.strip():
        raise RuntimeError("another ShellCrash preparation process is still running")

    secret_state, _ = run(
        gw,
        f"secret=$(sed -n 's/^secret=//p' {CRASHDIR}/configs/ShellCrash.cfg 2>/dev/null | head -n 1); "
        "if printf '%s\\n' \"$secret\" | grep -Eq '^[A-Za-z0-9._-]{12,64}$'; "
        "then echo CONTROLLER_SECRET_CONFIGURED; "
        "else echo CONTROLLER_SECRET_REQUIRED; fi",
        timeout=15,
        required=False,
    )
    if "CONTROLLER_SECRET_CONFIGURED" not in secret_state:
        secret = getpass.getpass(
            "Create Mihomo Controller password (12-64 chars, hidden): "
        ).strip()
        secret_confirm = getpass.getpass("Confirm Controller password (hidden): ").strip()
        if secret != secret_confirm:
            raise RuntimeError("Controller passwords do not match")
        if not re.fullmatch(r"[A-Za-z0-9._-]{12,64}", secret):
            raise RuntimeError(
                "Controller password must use 12-64 ASCII letters, numbers, dots, underscores, or hyphens"
            )
        with tempfile.NamedTemporaryFile(
            prefix="d01_controller_secret_", delete=False, mode="w", encoding="ascii"
        ) as secret_file:
            secret_temp = secret_file.name
            secret_file.write(secret)
        if not gw.upload(secret_temp, REMOTE_SECRET):
            raise RuntimeError("could not upload the Controller credential")
        configured, configured_rc = run(
            gw,
            f"chmod 0600 {REMOTE_SECRET} && CRASHDIR={CRASHDIR} && export CRASHDIR && "
            f". {CRASHDIR}/libs/set_config.sh && secret=$(cat {REMOTE_SECRET}) && "
            f"setconfig secret \"$secret\" && "
            f"saved=$(sed -n 's/^secret=//p' {CRASHDIR}/configs/ShellCrash.cfg | head -n 1) && "
            f"requested=$(cat {REMOTE_SECRET}) && test \"$saved\" = \"$requested\" && "
            "printf '%s\\n' \"$saved\" | grep -Eq '^[A-Za-z0-9._-]{12,64}$' && "
            f"chmod 0600 {CRASHDIR}/configs/ShellCrash.cfg && echo CONTROLLER_SECRET_CONFIGURED",
            timeout=25,
            required=False,
        )
        if configured_rc != 0 or "CONTROLLER_SECRET_CONFIGURED" not in configured:
            raise RuntimeError("Controller credential was not persisted")

    secret_permissions, secret_permissions_rc = run(
        gw,
        f"chmod 0600 {CRASHDIR}/configs/ShellCrash.cfg && "
        f"test \"$(ls -l {CRASHDIR}/configs/ShellCrash.cfg | awk '{{print $1}}')\" = '-rw-------' && "
        "echo CONTROLLER_SECRET_FILE_MODE_OK",
        timeout=15,
        required=False,
    )
    if secret_permissions_rc != 0 or "CONTROLLER_SECRET_FILE_MODE_OK" not in secret_permissions:
        raise RuntimeError("could not restrict the persistent Controller credential to root")

    prepared, prepared_rc = run(
        gw,
        f"rm -rf {TMPDIR}; mkdir -p {TMPDIR}; "
        f"CRASHDIR={CRASHDIR}; export CRASHDIR; "
        f"sh {CRASHDIR}/starts/bfstart.sh >{TMPDIR}/d01-bfstart.stdout "
        f"2>{TMPDIR}/d01-bfstart.stderr; rc=$?; "
        f"tail -n 16 {TMPDIR}/d01-bfstart.stderr {TMPDIR}/d01-bfstart.stdout 2>/dev/null; exit $rc",
        timeout=180,
        required=False,
    )
    if prepared_rc != 0:
        raise RuntimeError("ShellCrash runtime generation failed")
    protected, protected_rc = run(
        gw,
        f"chmod 0600 {TMPDIR}/config.yaml {TMPDIR}/d01-bfstart.stdout "
        f"{TMPDIR}/d01-bfstart.stderr 2>/dev/null && "
        f"test \"$(stat -c '%a' {TMPDIR}/config.yaml 2>/dev/null)\" = 600 && "
        "echo RUNTIME_PRIVATE_MODE_OK",
        timeout=20,
        required=False,
    )
    if protected_rc != 0 or "RUNTIME_PRIVATE_MODE_OK" not in protected:
        raise RuntimeError("could not protect the generated runtime credentials")

    link, link_rc = run(
        gw,
        f"rm -f {TMPDIR}/CrashCore; ln -s {CRASHDIR}/CrashCore.upx {TMPDIR}/CrashCore && "
        f"test -x {TMPDIR}/CrashCore && echo RUNTIME_CORE_LINK_READY",
        timeout=20,
        required=False,
    )
    if link_rc != 0 or "RUNTIME_CORE_LINK_READY" not in link:
        raise RuntimeError("could not create the runtime core link")

    fields, fields_rc = run(
        gw,
        f"test -s {TMPDIR}/config.yaml && "
        f"test \"$(grep -Ec '^redir-port:' {TMPDIR}/config.yaml)\" -eq 1 && "
        f"grep -q '^redir-port: 7892$' {TMPDIR}/config.yaml && "
        f"test \"$(grep -Ec '^external-controller:' {TMPDIR}/config.yaml)\" -eq 1 && "
        f"grep -q '^external-controller: :9999$' {TMPDIR}/config.yaml && "
        f"test \"$(grep -Ec '^secret:' {TMPDIR}/config.yaml)\" -eq 1 && "
        f"runtime_secret=$(sed -n 's/^secret:[[:space:]]*//p' {TMPDIR}/config.yaml | head -n 1) && "
        f"saved_secret=$(sed -n 's/^secret=//p' {CRASHDIR}/configs/ShellCrash.cfg | head -n 1) && "
        "test \"$runtime_secret\" = \"$saved_secret\" && "
        "printf '%s\\n' \"$runtime_secret\" | grep -Eq '^[A-Za-z0-9._-]{12,64}$' && "
        f"test \"$(grep -Ec '^dns:' {TMPDIR}/config.yaml)\" -eq 1 && "
        f"dns_fields=$(sed -n '/^dns:/,/^[A-Za-z][A-Za-z0-9_-]*:/p' {TMPDIR}/config.yaml) && "
        "test \"$(printf '%s\\n' \"$dns_fields\" | grep -Ec '^[[:space:]]+enable:')\" -eq 1 && "
        "printf '%s\\n' \"$dns_fields\" | "
        "grep -Eq '^[[:space:]]+enable:[[:space:]]*true[[:space:]]*(#.*)?$' && "
        "test \"$(printf '%s\\n' \"$dns_fields\" | grep -Ec '^[[:space:]]+listen:')\" -eq 1 && "
        "printf '%s\\n' \"$dns_fields\" | "
        "grep -Eq \"^[[:space:]]+listen:[[:space:]]*['\\\"]?:1053['\\\"]?[[:space:]]*(#.*)?$\" && "
        "test \"$(printf '%s\\n' \"$dns_fields\" | grep -Ec '^[[:space:]]+ipv6:')\" -eq 1 && "
        "printf '%s\\n' \"$dns_fields\" | "
        "grep -Eq '^[[:space:]]+ipv6:[[:space:]]*false[[:space:]]*(#.*)?$' && "
        "test \"$(printf '%s\\n' \"$dns_fields\" | grep -Ec '^[[:space:]]+enhanced-mode:')\" -eq 1 && "
        "printf '%s\\n' \"$dns_fields\" | "
        "grep -Eq '^[[:space:]]+enhanced-mode:[[:space:]]*redir-host[[:space:]]*(#.*)?$' && "
        "! printf '%s\\n' \"$dns_fields\" | grep -Eq 'fake-ip-range|fake-ip-filter' && "
        f"test \"$(grep -Ec '^tun:' {TMPDIR}/config.yaml)\" -eq 1 && "
        f"grep -Eq '^tun:[[:space:]]*\\{{[[:space:]]*enable:[[:space:]]*false[[:space:]]*\\}}[[:space:]]*$' "
        f"{TMPDIR}/config.yaml && "
        "echo RUNTIME_REDIR_HOST_FIELDS_OK",
        timeout=30,
        required=False,
    )
    if fields_rc != 0 or "RUNTIME_REDIR_HOST_FIELDS_OK" not in fields:
        raise RuntimeError("generated runtime is not the D01 redir-host baseline")

    valid, valid_rc = run(
        gw,
        f"{CRASHDIR}/CrashCore.upx -t -d {CRASHDIR} -f {TMPDIR}/config.yaml "
        f">{TMPDIR}/d01-runtime-test.log 2>&1; rc=$?; "
        f"tail -n 16 {TMPDIR}/d01-runtime-test.log; exit $rc",
        timeout=120,
        required=False,
    )
    if valid_rc != 0:
        raise RuntimeError("Mihomo rejected the generated runtime")
    run(gw, f"chmod 0600 {TMPDIR}/d01-runtime-test.log 2>/dev/null", required=False)

    print("RUNTIME_REDIR_HOST_VALID")
    print("CONTROLLER_AUTH=SECRET_REQUIRED_HTTP_401")
    print("RUNTIME_PREPARED_NOT_STARTED")
    print("AUTOSTART_DISABLED_UNTIL_TESTED")
except Exception as error:
    print(f"RUNTIME_PREPARE_FAILED: {error}")
    print("No interception rules were intentionally enabled.")
    raise SystemExit(2)
finally:
    try:
        run(gw, f"rm -f {REMOTE_SECRET}", timeout=10, required=False)
    except Exception:
        pass
    if secret_temp and os.path.exists(secret_temp):
        try:
            os.remove(secret_temp)
        except OSError:
            pass
