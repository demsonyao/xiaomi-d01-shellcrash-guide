#!/usr/bin/env python3
"""Install the reviewed local Zashboard bundle without starting Mihomo."""

import getpass
import hashlib
import os
import re
import tempfile

import gateway


PACKAGE = os.path.abspath(os.path.join("..", "shellcrash-package", "zashboard.tar.gz"))
EXPECTED_SHA256 = "a16e688c6774ae0bc17ec7364fb8c8825b752a65afe8ff5be3dffddea96c2128"
CRASHDIR = "/data/ShellCrash"
REMOTE_PACKAGE = "/tmp/zashboard.tar.gz"
REMOTE_SECRET = "/tmp/.zashboard_secret"
REMOTE_CFG_BACKUP = "/tmp/ShellCrash.cfg.zashboard-before-install"
DASHBOARD_PORT = 9999
ROUTER_IP = "192.168.31.1"


secret = getpass.getpass(
    "Create Mihomo Controller password for Zashboard (12-64 chars, hidden): "
).strip()
secret_confirm = getpass.getpass("Confirm Controller password (hidden): ").strip()
if secret != secret_confirm:
    raise SystemExit("ERROR: Controller passwords do not match")
if not re.fullmatch(r"[A-Za-z0-9._-]{12,64}", secret):
    raise SystemExit("ERROR: Use 12-64 ASCII letters, numbers, dots, underscores, or hyphens")

hasher = hashlib.sha256()
with open(PACKAGE, "rb") as package_file:
    for chunk in iter(lambda: package_file.read(1024 * 1024), b""):
        hasher.update(chunk)
actual_sha256 = hasher.hexdigest()
if actual_sha256 != EXPECTED_SHA256:
    raise SystemExit(f"ERROR: Zashboard package SHA256 mismatch: {actual_sha256}")

secret_temp = None
gw = None
ui_replaced = False
cfg_backup_ready = False
install_complete = False
runtime_prepared = False
runtime_invalidated = False
try:
    gw = gateway.Gateway()
    preflight = gw.run_cmd(
        f"test -s {CRASHDIR}/CrashCore.upx && "
        f"test -s {CRASHDIR}/configs/ShellCrash.cfg && "
        "test -z \"$(pidof CrashCore 2>/dev/null)\" && "
        "command -v iptables-save >/dev/null 2>&1 && rules=$(iptables-save 2>/dev/null) && "
        "refs=$(printf '%s\\n' \"$rules\" | grep -Eic 'shellcrash|clash|mihomo' || true) && "
        "test \"${refs:-0}\" -eq 0 && echo ZASHBOARD_PREFLIGHT_OK",
        die_on_error=False,
        timeout=20,
    ) or ""
    if gw.errcode != 0 or "ZASHBOARD_PREFLIGHT_OK" not in preflight:
        raise RuntimeError("Mihomo must be installed, stopped, and have no interception rules")

    existing_ui = gw.run_cmd(
        f"if test -e {CRASHDIR}/ui/index.html || test -e {CRASHDIR}/ui/CNAME || "
        f"test -n \"$(ls -A {CRASHDIR}/ui 2>/dev/null)\"; then "
        "echo EXISTING_UI_CONTENT; fi",
        die_on_error=False,
        timeout=15,
    ) or ""
    if "EXISTING_UI_CONTENT" in existing_ui:
        raise RuntimeError("A non-empty local Dashboard directory already exists; refusing to overwrite it")

    runtime_state = gw.run_cmd(
        "test -s /tmp/ShellCrash/config.yaml && echo PREPARED_RUNTIME_PRESENT || "
        "echo PREPARED_RUNTIME_ABSENT",
        die_on_error=False,
        timeout=10,
    ) or ""
    runtime_prepared = "PREPARED_RUNTIME_PRESENT" in runtime_state

    safety_lock = gw.run_cmd(
        f"touch {CRASHDIR}/.dis_startup && chmod 0600 {CRASHDIR}/.dis_startup && "
        f"test -f {CRASHDIR}/.dis_startup && echo AUTOSTART_SAFETY_LOCKED",
        die_on_error=False,
        timeout=15,
    ) or ""
    if gw.errcode != 0 or "AUTOSTART_SAFETY_LOCKED" not in safety_lock:
        raise RuntimeError("Cannot create and verify the ShellCrash autostart safety lock")

    backup = gw.run_cmd(
        f"rm -f {REMOTE_CFG_BACKUP} && "
        f"cp -p {CRASHDIR}/configs/ShellCrash.cfg {REMOTE_CFG_BACKUP} && "
        f"chmod 0600 {REMOTE_CFG_BACKUP} && test -s {REMOTE_CFG_BACKUP} && "
        "echo SHELLCRASH_CFG_BACKUP_READY",
        die_on_error=False,
        timeout=20,
    ) or ""
    if gw.errcode != 0 or "SHELLCRASH_CFG_BACKUP_READY" not in backup:
        raise RuntimeError("Cannot create the protected ShellCrash configuration backup")
    cfg_backup_ready = True

    with tempfile.NamedTemporaryFile(prefix="zashboard_secret_", delete=False, mode="w", encoding="ascii") as file:
        secret_temp = file.name
        file.write(secret)

    print(f"Uploading reviewed Zashboard package ({actual_sha256}) ...")
    if not gw.upload(PACKAGE, REMOTE_PACKAGE):
        raise RuntimeError("Cannot upload Zashboard package")
    if not gw.upload(secret_temp, REMOTE_SECRET):
        raise RuntimeError("Cannot upload Dashboard credential")
    protected_secret = gw.run_cmd(
        f"chmod 0600 {REMOTE_SECRET} && "
        f"test \"$(ls -l {REMOTE_SECRET} | awk '{{print $1}}')\" = '-rw-------' && "
        "echo CONTROLLER_SECRET_UPLOAD_MODE_OK",
        die_on_error=False,
        timeout=15,
    ) or ""
    if gw.errcode != 0 or "CONTROLLER_SECRET_UPLOAD_MODE_OK" not in protected_secret:
        raise RuntimeError("Cannot restrict the uploaded Controller credential to root")

    commands = [
        "rm -rf /tmp/zashboard-stage; mkdir -p /tmp/zashboard-stage; tar -zxf /tmp/zashboard.tar.gz -C /tmp/zashboard-stage",
        "test -s /tmp/zashboard-stage/index.html -a -s /tmp/zashboard-stage/CNAME",
        "size=$(du -sk /tmp/zashboard-stage | awk '{print $1}'); test \"$size\" -gt 100 -a \"$size\" -lt 8192",
        f"rm -rf {CRASHDIR}/ui; mkdir -p {CRASHDIR}/ui; cp -rf /tmp/zashboard-stage/. {CRASHDIR}/ui/",
        f"sed -i 's/127.0.0.1/{ROUTER_IP}/g; s/9090/{DASHBOARD_PORT}/g' {CRASHDIR}/ui/assets/*.js",
        (
            f"CRASHDIR={CRASHDIR}; export CRASHDIR; . {CRASHDIR}/libs/set_config.sh && "
            f"secret=$(cat {REMOTE_SECRET}) && setconfig secret \"$secret\" && "
            f"setconfig db_port {DASHBOARD_PORT} && setconfig host {ROUTER_IP} && "
            f"setconfig hostdir \"':{DASHBOARD_PORT}/ui'\" && "
            "setconfig external_ui_url https://github.com/Zephyruso/zashboard/releases/latest/download/dist-cdn-fonts.zip"
        ),
        f"rm -rf /tmp/zashboard-stage; rm -f {REMOTE_PACKAGE}",
    ]

    for index, command in enumerate(commands):
        if index == 3:
            ui_replaced = True
        output = gw.run_cmd(command, die_on_error=False, timeout=60)
        print(output or "")
        if gw.errcode != 0:
            raise RuntimeError(f"Router Dashboard installation command failed (rc={gw.errcode})")

    validation = gw.run_cmd(
        f"test -s {CRASHDIR}/ui/index.html && test -s {CRASHDIR}/ui/CNAME && "
        f"secret=$(sed -n 's/^secret=//p' {CRASHDIR}/configs/ShellCrash.cfg | head -n 1) && "
        f"requested=$(cat {REMOTE_SECRET}) && test \"$secret\" = \"$requested\" && "
        f"test ${{#secret}} -ge 12 && chmod 0600 {CRASHDIR}/configs/ShellCrash.cfg && "
        "echo ZASHBOARD_FILES_AND_CONTROLLER_SECRET_OK",
        die_on_error=False,
        timeout=20,
    ) or ""
    if gw.errcode != 0 or "ZASHBOARD_FILES_AND_CONTROLLER_SECRET_OK" not in validation:
        raise RuntimeError("Dashboard files or Controller credential did not validate")

    if runtime_prepared:
        invalidated = gw.run_cmd(
            "rm -f /tmp/ShellCrash/config.yaml && "
            "test ! -e /tmp/ShellCrash/config.yaml && echo PREPARED_RUNTIME_INVALIDATED",
            die_on_error=False,
            timeout=15,
        ) or ""
        if gw.errcode != 0 or "PREPARED_RUNTIME_INVALIDATED" not in invalidated:
            raise RuntimeError("Cannot invalidate the prepared runtime after changing the Controller secret")
        runtime_invalidated = True

    backup_removed = gw.run_cmd(
        f"rm -f {REMOTE_CFG_BACKUP} && test ! -e {REMOTE_CFG_BACKUP} && "
        "echo SHELLCRASH_CFG_BACKUP_REMOVED",
        die_on_error=False,
        timeout=15,
    ) or ""
    if gw.errcode != 0 or "SHELLCRASH_CFG_BACKUP_REMOVED" not in backup_removed:
        raise RuntimeError("Cannot remove the temporary ShellCrash configuration backup")
    cfg_backup_ready = False
    install_complete = True

    checks = [
        f"du -sh {CRASHDIR}/ui; test -s {CRASHDIR}/ui/index.html && echo DASHBOARD_FILES_OK",
        f"grep -E '^(db_port|host|hostdir|external_ui_url)=' {CRASHDIR}/configs/ShellCrash.cfg",
        "df -h /data /tmp",
        "pidof CrashCore 2>/dev/null || echo CORE_NOT_RUNNING",
        f"test -f {CRASHDIR}/.dis_startup && echo AUTOSTART_DISABLED_UNTIL_TESTED",
    ]
    for command in checks:
        print(f"\n### {command}")
        print(gw.run_cmd(command, die_on_error=False, timeout=20) or "")

    if runtime_prepared:
        print("PREPARED_RUNTIME_INVALIDATED_REPREPARE_REQUIRED")
    persistent_config = gw.run_cmd(
        f"test -s {CRASHDIR}/yamls/config.yaml && echo PERSISTENT_CONFIG_READY",
        die_on_error=False,
        timeout=10,
    ) or ""
    if "PERSISTENT_CONFIG_READY" in persistent_config:
        print("NEXT_REQUIRED=prepare_d01_runtime_redir_host.py")
    else:
        print("NEXT_REQUIRED=import_d01_full_yaml.py")
    print(f"ZASHBOARD_INSTALLED_NOT_STARTED=http://{ROUTER_IP}:{DASHBOARD_PORT}/ui/")
except Exception:
    if gw is not None and not install_complete:
        if cfg_backup_ready:
            try:
                restored = gw.run_cmd(
                    f"test -s {REMOTE_CFG_BACKUP} && "
                    f"cp -f {REMOTE_CFG_BACKUP} {CRASHDIR}/configs/ShellCrash.cfg.restore && "
                    f"chmod 0600 {CRASHDIR}/configs/ShellCrash.cfg.restore && "
                    f"mv -f {CRASHDIR}/configs/ShellCrash.cfg.restore "
                    f"{CRASHDIR}/configs/ShellCrash.cfg && "
                    "echo SHELLCRASH_CFG_ATOMICALLY_RESTORED",
                    die_on_error=False,
                    timeout=20,
                ) or ""
                if gw.errcode == 0 and "SHELLCRASH_CFG_ATOMICALLY_RESTORED" in restored:
                    cfg_backup_ready = False
                    gw.run_cmd(f"rm -f {REMOTE_CFG_BACKUP}", die_on_error=False, timeout=10)
                else:
                    print(f"SHELLCRASH_CFG_RESTORE_UNCONFIRMED_BACKUP_RETAINED={REMOTE_CFG_BACKUP}")
            except Exception:
                print(f"SHELLCRASH_CFG_RESTORE_UNCONFIRMED_BACKUP_RETAINED={REMOTE_CFG_BACKUP}")
        if ui_replaced:
            try:
                gw.run_cmd(f"rm -rf {CRASHDIR}/ui", die_on_error=False, timeout=20)
            except Exception:
                pass
        if runtime_invalidated:
            print("PREPARED_RUNTIME_REQUIRES_REBUILD_AFTER_FAILED_INSTALL")
    raise
finally:
    if gw is not None:
        try:
            backup_cleanup = f" {REMOTE_CFG_BACKUP}" if not cfg_backup_ready else ""
            gw.run_cmd(
                f"rm -rf /tmp/zashboard-stage; "
                f"rm -f {REMOTE_PACKAGE} {REMOTE_SECRET} "
                f"{CRASHDIR}/configs/ShellCrash.cfg.restore{backup_cleanup}",
                die_on_error=False,
                timeout=20,
            )
        except Exception:
            pass
    if secret_temp and os.path.exists(secret_temp):
        try:
            os.remove(secret_temp)
        except OSError:
            pass
