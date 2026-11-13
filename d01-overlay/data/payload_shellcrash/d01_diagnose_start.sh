#!/bin/sh

CRASHDIR=/data/ShellCrash
TMPDIR=/tmp/ShellCrash
. "$CRASHDIR/configs/command.env" 2>/dev/null
. "$CRASHDIR/configs/ShellCrash.cfg" 2>/dev/null

echo DIAGNOSTIC_BEGIN
[ -f "$CRASHDIR/.dis_startup" ] && echo AUTOSTART_LOCK=ON || echo AUTOSTART_LOCK=OFF
[ -f "$CRASHDIR/.start_error" ] && echo SHELLCRASH_START_ERROR_FLAG=YES || echo SHELLCRASH_START_ERROR_FLAG=NO
[ "$redir_mod" = "Redir模式" ] && echo REDIR_MODE_VALUE=OK || echo REDIR_MODE_VALUE=MISMATCH
printf 'REDIR_MODE_UTF8_HEX='
printf '%s' "$redir_mod" | od -An -tx1 | tr -d ' \n'
echo
printf 'PROCESS1='
cat /proc/1/comm 2>/dev/null
printf 'CORE_PID='
pidof CrashCore 2>/dev/null || echo NONE
printf 'COMMANDS='
for command_name in nohup setsid iptables iptables-save ipset curl sed awk; do
    command -v "$command_name" >/dev/null 2>&1 && printf '%s=OK ' "$command_name" || printf '%s=MISSING ' "$command_name"
done
echo

echo RUNTIME_FILES
ls -lh "$TMPDIR/config.yaml" "$TMPDIR/core_test.log" "$TMPDIR/debug.log" "$TMPDIR/ShellCrash.log" 2>&1

for log_file in "$TMPDIR/core_test.log" "$TMPDIR/debug.log" "$TMPDIR/ShellCrash.log"; do
    if [ -s "$log_file" ]; then
        echo "LOG_BEGIN=$(basename "$log_file")"
        tail -n 100 "$log_file" |
            sed -E 's#(password|uuid|public-key|short-id)([=:][^, }]+)#\1=<redacted>#g'
        echo "LOG_END=$(basename "$log_file")"
    fi
done

if [ -s "$TMPDIR/config.yaml" ]; then
    echo RUNTIME_CONFIG_TEST_BEGIN
    "$CRASHDIR/CrashCore.upx" -t -d "$TMPDIR" -f "$TMPDIR/config.yaml" 2>&1
    echo "RUNTIME_CONFIG_TEST_RC=$?"
else
    echo RUNTIME_CONFIG_MISSING
fi
echo DIAGNOSTIC_END
