#!/bin/sh

TX=/tmp/d01-shellcrash-transaction
TOKEN=${1-}
SCRIPT=/tmp/d01_shellcrash_firewall_failsafe.sh
MAINTENANCE=/tmp/d01-stability/maintenance
MAINTENANCE_OWNER=/tmp/d01-stability/maintenance.owner
CRASHDIR=/data/ShellCrash

registration_failed() {
    if [ "$(cat "$TX/owner" 2>/dev/null)" = "$TOKEN" ]; then
        [ "$(cat "$TX/pid" 2>/dev/null)" = "$$" ] && rm -f "$TX/pid" "$TX/start" "$TX/armed"
        rm -f "$TX/pid.new" "$TX/start.new" "$TX/armed.new"
    fi
    exit 1
}

cleanup_transaction() {
    [ "$(cat "$TX/owner" 2>/dev/null)" = "$TOKEN" ] || return 1
    [ "$(cat "$TX/pid" 2>/dev/null)" = "$$" ] || return 1
    if [ "$(cat "$MAINTENANCE_OWNER" 2>/dev/null)" = "$TOKEN" ]; then
        rm -f "$MAINTENANCE" "$MAINTENANCE_OWNER"
    fi
    rm -f "$TX/action" "$TX/action.new" "$TX/claim.watchdog.$$" "$TX/claim.watchdog.$$.new" "$TX/claim.python.$TOKEN" "$TX/claim.python.$TOKEN.new"
    for f in owner owner.new kind kind.new script script.new pid pid.new start start.new armed armed.new mutation mutation.new ok ok.new rollback-request rollback-request.new; do
        rm -f "$TX/$f"
    done
    rmdir "$TX" 2>/dev/null
}

claim_action() {
    claim="$TX/claim.watchdog.$$"
    printf '%s\n' "watchdog:$TOKEN:$1" >"$claim.new" && mv -f "$claim.new" "$claim" || return 1
    ln "$claim" "$TX/action" 2>/dev/null
    result=$?
    rm -f "$claim"
    return "$result"
}

[ -n "$TOKEN" ] || exit 1
[ "$(cat "$TX/owner" 2>/dev/null)" = "$TOKEN" ] || exit 1
[ "$(cat "$TX/script" 2>/dev/null)" = "$SCRIPT" ] || exit 1
START=$(awk '{print $22; exit}' "/proc/$$/stat" 2>/dev/null)
case "$START" in ''|*[!0-9]*) exit 1;; esac
printf '%s\n' "$$" >"$TX/pid.new" && mv -f "$TX/pid.new" "$TX/pid" || registration_failed
printf '%s\n' "$START" >"$TX/start.new" && mv -f "$TX/start.new" "$TX/start" || registration_failed
[ "$(cat "$TX/pid" 2>/dev/null)" = "$$" ] || registration_failed
[ "$(cat "$TX/start" 2>/dev/null)" = "$START" ] || registration_failed
[ -r "/proc/$$/cmdline" ] || registration_failed
tr '\000' '\n' <"/proc/$$/cmdline" 2>/dev/null | awk -v wanted="$SCRIPT" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1 || registration_failed
tr '\000' '\n' <"/proc/$$/cmdline" 2>/dev/null | awk -v wanted="$TOKEN" '$0 == wanted {found=1} END {if (!found) exit 1}' >/dev/null 2>&1 || registration_failed
INTERRUPTED=0
trap 'INTERRUPTED=1' HUP INT TERM
printf '%s\n' "$TOKEN" >"$TX/armed.new" && mv -f "$TX/armed.new" "$TX/armed" || registration_failed
[ "$(cat "$TX/armed" 2>/dev/null)" = "$TOKEN" ] || registration_failed
WAITED=0
while [ "$WAITED" -lt 180 ] && [ "$INTERRUPTED" -eq 0 ]; do
    sleep 1
    WAITED=$((WAITED + 1))
done

[ "$(cat "$TX/owner" 2>/dev/null)" = "$TOKEN" ] || exit 0
[ "$(cat "$TX/pid" 2>/dev/null)" = "$$" ] || exit 0
[ "$(cat "$TX/start" 2>/dev/null)" = "$START" ] || exit 0
[ "$(awk '{print $22; exit}' "/proc/$$/stat" 2>/dev/null)" = "$START" ] || exit 0
[ "$(cat "$TX/armed" 2>/dev/null)" = "$TOKEN" ] || exit 0

MODE=cleanup
if [ "$(cat "$TX/mutation" 2>/dev/null)" = "$TOKEN" ] && [ "$(cat "$TX/ok" 2>/dev/null)" != "$TOKEN" ]; then
    MODE=rollback
fi
claim_action "$MODE" || true
ACTION=$(cat "$TX/action" 2>/dev/null)
case "$ACTION" in
"python:$TOKEN:release")
    GRACE=0
    while [ "$GRACE" -lt 5 ] && [ "$(cat "$TX/ok" 2>/dev/null)" != "$TOKEN" ]; do sleep 1; GRACE=$((GRACE + 1)); done
    if [ "$(cat "$TX/ok" 2>/dev/null)" = "$TOKEN" ]; then MODE=cleanup; else MODE=rollback; fi
    ;;
"python:$TOKEN:rollback"|"watchdog:$TOKEN:rollback") MODE=rollback ;;
"watchdog:$TOKEN:cleanup") MODE=cleanup ;;
*) exit 0 ;;
esac
if [ "$MODE" = cleanup ]; then
    cleanup_transaction
    exit 0
fi

(
    export CRASHDIR
    touch "$CRASHDIR/.dis_startup"
    if [ -r "$CRASHDIR/libs/get_config.sh" ] && [ -x "$CRASHDIR/starts/fw_stop.sh" ]; then
        ( . "$CRASHDIR/libs/get_config.sh"; . "$CRASHDIR/starts/fw_stop.sh" ) || true
    fi
) >/tmp/shellcrash_firewall_failsafe.log 2>&1
sleep 2

SAFE=0
if command -v iptables-save >/dev/null 2>&1; then
    if RULES=$(iptables-save 2>/dev/null); then
        REFS=$(printf '%s\n' "$RULES" | grep -Eic 'shellcrash|clash|mihomo' || true)
        if [ "${REFS:-0}" -eq 0 ] && [ -f "$CRASHDIR/.dis_startup" ]; then
            SAFE=1
        fi
    fi
fi
[ "$SAFE" -eq 1 ] && cleanup_transaction
exit 0
