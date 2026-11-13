#!/usr/bin/env python3
"""Collect a read-only, credential-redacted ShellCrash start diagnostic."""

import os

import gateway


remote_script = "/tmp/d01_diagnose_shellcrash_start.sh"
local_script = os.path.join("data", "payload_shellcrash", "d01_diagnose_start.sh")

gw = gateway.Gateway()
if not gw.upload(local_script, remote_script):
    raise SystemExit("ERROR: Cannot upload temporary diagnostic script")

prepare = gw.run_cmd(
    f"tr -d '\\r' < {remote_script} > {remote_script}.lf && "
    f"mv {remote_script}.lf {remote_script} && chmod 0700 {remote_script}",
    die_on_error=False,
)
if prepare:
    print(prepare)
if gw.errcode != 0:
    raise SystemExit("ERROR: Cannot prepare diagnostic script")

output = gw.run_cmd(f"sh {remote_script}; rc=$?; rm -f {remote_script}; exit $rc", die_on_error=False, timeout=90)
print(output or "")
if gw.errcode != 0:
    raise SystemExit(f"ERROR: Diagnostic returned rc={gw.errcode}")
