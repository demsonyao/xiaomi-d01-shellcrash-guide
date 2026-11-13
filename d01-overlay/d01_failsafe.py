#!/usr/bin/env python3
"""Shared transaction guard for D01 routing changes.

The guard deliberately uses one router-wide lock for the controlled start,
firewall test, and boot-service test.  A unique token is passed as a distinct
argv element to the router-side watchdog, and the watchdog records its own PID
and Linux process start time before it sleeps.  This prevents an older timer,
a concurrent run, or a reused PID from being mistaken for the current run.
"""

import secrets


TRANSACTION_DIR = "/tmp/d01-shellcrash-transaction"
MAINTENANCE = "/tmp/d01-stability/maintenance"
MAINTENANCE_OWNER = "/tmp/d01-stability/maintenance.owner"


class RouterFailsafe:
    """Reserve, arm, mark, and disarm one router-side rollback transaction."""

    def __init__(self, runner, remote_script, kind, log_path, armed_message):
        self.runner = runner
        self.remote_script = remote_script
        self.kind = kind
        self.log_path = log_path
        self.armed_message = armed_message
        self.token = secrets.token_hex(16)
        self.reserved = False
        self.armed = False
        self.mutation_started = False
        self.rollback_claimed = False
        self.watchdog_completed = False
        self.watchdog_in_progress = False

    @staticmethod
    def _known_files():
        return (
            "owner owner.new kind kind.new script script.new pid pid.new start start.new "
            "armed armed.new mutation mutation.new ok ok.new action action.new "
            "rollback-request rollback-request.new boot_snapshot_ready "
            "boot_snapshot_ready.new prev_init prev_init_present prev_hook prev_hook_present "
            "prev_auto prev_auto_present prev_s95_file prev_s95_link prev_k10_file prev_k10_link "
            "prev_uci_present prev_uci_type prev_uci_option_type prev_uci_option_type_present "
            "prev_uci_path prev_uci_path_present "
            "prev_uci_enabled prev_uci_enabled_present"
        )

    def reserve(self):
        """Atomically reserve the shared slot; never auto-remove an unknown lock."""
        tx = TRANSACTION_DIR
        command = (
            f"tx={tx}; token={self.token}; "
            "if ! mkdir \"$tx\" 2>/dev/null; then "
            "owner=$(cat \"$tx/owner\" 2>/dev/null); kind=$(cat \"$tx/kind\" 2>/dev/null); "
            "pid=$(cat \"$tx/pid\" 2>/dev/null); "
            "echo TRANSACTION_RETRY_REFUSED_KIND=${kind:-unknown}; "
            "echo TRANSACTION_RETRY_REFUSED_PID=${pid:-unknown}; exit 3; fi; "
            "if chmod 0700 \"$tx\" && printf '%s\\n' \"$token\" >\"$tx/owner.new\" && mv -f \"$tx/owner.new\" \"$tx/owner\" && "
            f"printf '%s\\n' '{self.kind}' >\"$tx/kind.new\" && mv -f \"$tx/kind.new\" \"$tx/kind\" && "
            f"printf '%s\\n' '{self.remote_script}' >\"$tx/script.new\" && "
            "mv -f \"$tx/script.new\" \"$tx/script\"; then "
            "echo TRANSACTION_RESERVED=$token; exit 0; fi; "
            f"for f in {self._known_files()}; do rm -f \"$tx/$f\"; done; "
            "rmdir \"$tx\" 2>/dev/null || true; exit 1"
        )
        output, rc = self.runner(command, timeout=15, required=False)
        if rc != 0 or f"TRANSACTION_RESERVED={self.token}" not in output:
            if "TRANSACTION_RETRY_REFUSED" in output:
                raise RuntimeError("another D01 ShellCrash safety transaction is active or needs inspection")
            raise RuntimeError("could not reserve the D01 ShellCrash safety transaction")
        self.reserved = True

    def arm(self):
        """Launch the watchdog and verify its self-recorded PID/start time."""
        tx = TRANSACTION_DIR
        command = (
            f"tx={tx}; token={self.token}; script={self.remote_script}; "
            "test \"$(cat \"$tx/owner\" 2>/dev/null)\" = \"$token\" || exit 1; "
            "mkdir -p /tmp/d01-stability || exit 1; "
            "date +%s > /tmp/d01-stability/maintenance.new && "
            f"mv -f /tmp/d01-stability/maintenance.new {MAINTENANCE} && "
            "printf '%s\\n' \"$token\" > /tmp/d01-stability/maintenance.owner.new && "
            f"mv -f /tmp/d01-stability/maintenance.owner.new {MAINTENANCE_OWNER} || exit 1; "
            f"nohup \"$script\" \"$token\" >{self.log_path} 2>&1 & "
            "i=0; while [ $i -lt 10 ]; do "
            "owner=$(cat \"$tx/owner\" 2>/dev/null); armed=$(cat \"$tx/armed\" 2>/dev/null); "
            "pid=$(cat \"$tx/pid\" 2>/dev/null); saved=$(cat \"$tx/start\" 2>/dev/null); "
            "case \"$pid\" in ''|*[!0-9]*) valid=0;; *) valid=1;; esac; "
            "case \"$saved\" in ''|*[!0-9]*) valid=0;; esac; "
            "if [ \"$valid\" -eq 1 ] && [ \"$owner\" = \"$token\" ] && [ \"$armed\" = \"$token\" ] && "
            "[ -r \"/proc/$pid/stat\" ]; then current=$(awk '{print $22; exit}' \"/proc/$pid/stat\" 2>/dev/null); "
            "if [ \"$current\" = \"$saved\" ] && "
            "tr '\\000' '\\n' <\"/proc/$pid/cmdline\" 2>/dev/null | awk -v wanted=\"$script\" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1 && "
            "tr '\\000' '\\n' <\"/proc/$pid/cmdline\" 2>/dev/null | awk -v wanted=\"$token\" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1; then "
            f"echo {self.armed_message}; exit 0; fi; fi; i=$((i + 1)); sleep 1; done; "
            "echo FAILSAFE_SELF_REGISTRATION_FAILED; exit 1"
        )
        output, rc = self.runner(command, timeout=20, required=False)
        if rc != 0 or self.armed_message not in output:
            return False
        self.armed = True
        return True

    def mark_mutation(self):
        """Authorize timeout rollback immediately before the first real mutation."""
        tx = TRANSACTION_DIR
        command = (
            f"tx={tx}; token={self.token}; script={self.remote_script}; "
            "test \"$(cat \"$tx/owner\" 2>/dev/null)\" = \"$token\" || exit 1; "
            "test \"$(cat \"$tx/armed\" 2>/dev/null)\" = \"$token\" || exit 1; "
            "pid=$(cat \"$tx/pid\" 2>/dev/null); saved=$(cat \"$tx/start\" 2>/dev/null); "
            "case \"$pid\" in ''|*[!0-9]*) exit 1;; esac; "
            "case \"$saved\" in ''|*[!0-9]*) exit 1;; esac; "
            "test -r \"/proc/$pid/stat\" || exit 1; "
            "current=$(awk '{print $22; exit}' \"/proc/$pid/stat\" 2>/dev/null); "
            "test \"$current\" = \"$saved\" || exit 1; "
            "tr '\\000' '\\n' <\"/proc/$pid/cmdline\" 2>/dev/null | awk -v wanted=\"$script\" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1 || exit 1; "
            "tr '\\000' '\\n' <\"/proc/$pid/cmdline\" 2>/dev/null | awk -v wanted=\"$token\" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1 || exit 1; "
            "printf '%s\\n' \"$token\" >\"$tx/mutation.new\" && "
            "mv -f \"$tx/mutation.new\" \"$tx/mutation\" && "
            "test \"$(cat \"$tx/mutation\" 2>/dev/null)\" = \"$token\" && "
            "echo TRANSACTION_MUTATION_MARKED"
        )
        output, rc = self.runner(command, timeout=12, required=False)
        if rc != 0 or "TRANSACTION_MUTATION_MARKED" not in output:
            return False
        self.mutation_started = True
        return True

    def request_rollback(self):
        """Wake the verified watchdog and wait for its independently owned rollback."""
        tx = TRANSACTION_DIR
        command = (
            f"tx={tx}; token={self.token}; script={self.remote_script}; "
            "if ! test -d \"$tx\"; then echo TRANSACTION_WATCHDOG_COMPLETED; exit 0; fi; "
            "test \"$(cat \"$tx/owner\" 2>/dev/null)\" = \"$token\" || exit 1; "
            "test \"$(cat \"$tx/mutation\" 2>/dev/null)\" = \"$token\" || exit 1; "
            "pid=$(cat \"$tx/pid\" 2>/dev/null); saved=$(cat \"$tx/start\" 2>/dev/null); "
            "case \"$pid\" in ''|*[!0-9]*) exit 1;; esac; case \"$saved\" in ''|*[!0-9]*) exit 1;; esac; "
            "test -r \"/proc/$pid/stat\" || exit 1; current=$(awk '{print $22; exit}' \"/proc/$pid/stat\" 2>/dev/null); "
            "test \"$current\" = \"$saved\" || exit 1; "
            "tr '\\000' '\\n' <\"/proc/$pid/cmdline\" 2>/dev/null | awk -v wanted=\"$script\" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1 || exit 1; "
            "tr '\\000' '\\n' <\"/proc/$pid/cmdline\" 2>/dev/null | awk -v wanted=\"$token\" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1 || exit 1; "
            "printf '%s\\n' \"$token\" >\"$tx/rollback-request.new\" && "
            "mv -f \"$tx/rollback-request.new\" \"$tx/rollback-request\" || exit 1; "
            "kill -TERM \"$pid\" 2>/dev/null || exit 1; "
            "i=0; while [ $i -lt 50 ] && test -d \"$tx\"; do sleep 1; i=$((i + 1)); done; "
            "if test -d \"$tx\"; then echo TRANSACTION_WATCHDOG_IN_PROGRESS; exit 6; "
            "else echo TRANSACTION_WATCHDOG_COMPLETED; exit 0; fi"
        )
        output, rc = self.runner(command, timeout=58, required=False)
        self.watchdog_completed = rc == 0 and "TRANSACTION_WATCHDOG_COMPLETED" in output
        self.watchdog_in_progress = "TRANSACTION_WATCHDOG_IN_PROGRESS" in output
        if self.watchdog_completed:
            self.reserved = False
            self.armed = False
            self.mutation_started = False
        return self.watchdog_completed

    def release(self, allow_mutated=False, require_armed=False):
        """Stop only the token-matching watchdog, then remove only our metadata."""
        tx = TRANSACTION_DIR
        mutation_check = "true" if allow_mutated else "test ! -s \"$tx/mutation\""
        armed_check = (
            "test \"$(cat \"$tx/armed\" 2>/dev/null)\" = \"$token\""
            if require_armed
            else "true"
        )
        command = (
            f"tx={tx}; token={self.token}; script={self.remote_script}; "
            "if ! test -d \"$tx\"; then echo TRANSACTION_WATCHDOG_COMPLETED; exit 5; fi; "
            "test \"$(cat \"$tx/owner\" 2>/dev/null)\" = \"$token\" || exit 1; "
            f"{mutation_check} || exit 1; {armed_check} || exit 1; "
            "pid=$(cat \"$tx/pid\" 2>/dev/null); saved=$(cat \"$tx/start\" 2>/dev/null); match=0; "
            "case \"$pid\" in ''|*[!0-9]*) valid=0;; *) valid=1;; esac; "
            "case \"$saved\" in ''|*[!0-9]*) valid=0;; esac; "
            "if [ \"$valid\" -eq 1 ]; then "
            "if [ -r \"/proc/$pid/stat\" ]; then current=$(awk '{print $22; exit}' \"/proc/$pid/stat\" 2>/dev/null); "
            "if [ \"$current\" = \"$saved\" ] && "
            "tr '\\000' '\\n' <\"/proc/$pid/cmdline\" 2>/dev/null | awk -v wanted=\"$script\" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1 && "
            "tr '\\000' '\\n' <\"/proc/$pid/cmdline\" 2>/dev/null | awk -v wanted=\"$token\" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1; then match=1; fi; fi; fi; "
            f"if [ \"$match\" -ne 1 ] && {str(require_armed).lower()}; then exit 3; fi; "
            "claim=\"$tx/claim.python.$token\"; "
            "printf '%s\\n' \"python:$token:release\" >\"$claim.new\" && mv -f \"$claim.new\" \"$claim\" || exit 1; "
            "if ln \"$claim\" \"$tx/action\" 2>/dev/null; then :; fi; rm -f \"$claim\"; "
            "action=$(cat \"$tx/action\" 2>/dev/null); "
            "case \"$action\" in \"watchdog:$token:rollback\"|\"watchdog:$token:cleanup\") "
            "i=0; while [ $i -lt 40 ] && test -d \"$tx\"; do sleep 1; i=$((i + 1)); done; "
            "if test -d \"$tx\"; then echo TRANSACTION_WATCHDOG_IN_PROGRESS; exit 6; "
            "else echo TRANSACTION_WATCHDOG_COMPLETED; exit 5; fi;; "
            "\"python:$token:release\"|\"python:$token:rollback\") ;; *) "
            "echo TRANSACTION_ACTION_CLAIM_UNKNOWN; exit 7;; esac; "
            "if [ \"$match\" -eq 1 ]; then "
            "printf '%s\\n' \"$token\" >\"$tx/ok.new\" && mv -f \"$tx/ok.new\" \"$tx/ok\" || exit 1; "
            "kill \"$pid\" 2>/dev/null || true; i=0; while [ $i -lt 5 ] && kill -0 \"$pid\" 2>/dev/null; do "
            "sleep 1; i=$((i + 1)); done; "
            "if [ -r \"/proc/$pid/stat\" ]; then current=$(awk '{print $22; exit}' \"/proc/$pid/stat\" 2>/dev/null); "
            "if [ \"$current\" = \"$saved\" ] && "
            "tr '\\000' '\\n' <\"/proc/$pid/cmdline\" 2>/dev/null | awk -v wanted=\"$script\" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1 && "
            "tr '\\000' '\\n' <\"/proc/$pid/cmdline\" 2>/dev/null | awk -v wanted=\"$token\" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1; then exit 2; fi; fi; "
            "fi; rm -f \"$tx/action\" \"$tx/action.new\" \"$tx/claim.python.$token\" \"$tx/claim.python.$token.new\"; "
            f"if [ \"$(cat {MAINTENANCE_OWNER} 2>/dev/null)\" = \"$token\" ]; then "
            f"rm -f {MAINTENANCE} {MAINTENANCE_OWNER}; fi; "
            f"for f in {self._known_files()}; do rm -f \"$tx/$f\"; done; "
            "rmdir \"$tx\" 2>/dev/null || { test ! -d \"$tx\" || exit 4; }; echo TRANSACTION_RELEASED"
        )
        output, rc = self.runner(command, timeout=55, required=False)
        released = rc == 0 and "TRANSACTION_RELEASED" in output
        self.watchdog_completed = "TRANSACTION_WATCHDOG_COMPLETED" in output
        self.watchdog_in_progress = "TRANSACTION_WATCHDOG_IN_PROGRESS" in output
        if self.watchdog_completed:
            self.reserved = False
            self.armed = False
            self.mutation_started = False
        if released:
            self.reserved = False
            self.armed = False
            self.mutation_started = False
            self.rollback_claimed = False
        return released
