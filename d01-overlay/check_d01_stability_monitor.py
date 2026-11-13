#!/usr/bin/env python3
"""Read-only status check for the optional D01 stability monitor."""

import gateway


BASE = "/data/d01-stability"
RUNDIR = "/tmp/d01-stability"
MONITOR = f"{BASE}/monitor.sh"


def run(gw, command, timeout=25):
    output = gw.run_cmd(command, die_on_error=False, timeout=timeout) or ""
    if output:
        print(output)
    return output, gw.errcode


gw = gateway.Gateway()

command = (
    "echo '=== D01_STABILITY_MONITOR_STATUS ==='; "
    f"if test -x {MONITOR}; then echo MONITOR_FILE=YES; ls -lh {MONITOR} 2>&1; "
    "else echo MONITOR_FILE=NO; fi; running=0; "
    f"if test -s {RUNDIR}/monitor.pid; then pid=$(cat {RUNDIR}/monitor.pid 2>/dev/null); "
    "case \"$pid\" in ''|*[!0-9]*) ;; *) "
    f"if kill -0 \"$pid\" 2>/dev/null && tr '\\000' ' ' </proc/$pid/cmdline 2>/dev/null | "
    f"grep -Fq '{MONITOR} run'; then echo MONITOR_RUNNING_PID=$pid; running=1; fi;; esac; fi; "
    "if test \"$running\" -eq 0; then echo MONITOR_NOT_RUNNING; fi; "
    "printf 'ROUTER_UPTIME_SECONDS='; awk '{print int($1); exit}' /proc/uptime 2>/dev/null; "
    f"if test -s {RUNDIR}/ring.0.csv; then echo RUNTIME_RING0=YES; "
    f"ls -lh {RUNDIR}/ring.0.csv 2>&1; echo RING0_TAIL_BEGIN; "
    f"tail -n 4 {RUNDIR}/ring.0.csv 2>/dev/null; echo RING0_TAIL_END; "
    "else echo RUNTIME_RING0=NO; fi; "
    f"if test -s {RUNDIR}/ring.1.csv; then echo RUNTIME_RING1=YES; "
    f"ls -lh {RUNDIR}/ring.1.csv 2>&1; else echo RUNTIME_RING1=NO; fi; "
    f"if test -s {BASE}/last-trigger.txt; then echo PERSISTENT_TRIGGER_SNAPSHOT=YES; "
    f"ls -lh {BASE}/last-trigger.txt 2>&1; "
    f"grep -E '^(trigger_reason|trigger_time)=' {BASE}/last-trigger.txt 2>/dev/null; "
    "else echo PERSISTENT_TRIGGER_SNAPSHOT=NO; fi; echo CHECK_COMPLETE_NO_ROUTER_CHANGES"
)

output, rc = run(gw, command)
if rc != 0 or "CHECK_COMPLETE_NO_ROUTER_CHANGES" not in output:
    print(f"MONITOR_STATUS_CHECK_FAILED: router command rc={rc}")
    raise SystemExit(2)
