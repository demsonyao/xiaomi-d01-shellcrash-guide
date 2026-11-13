#!/bin/sh

# Snapshot and restore only the boot-registration files changed by the D01
# installer.  Routing is made direct and verified before any previous files are
# restored.  This helper is called both by Python and by the timeout watchdog.
TX=/tmp/d01-shellcrash-transaction
ACTION=${1-}
TOKEN=${2-}
CRASHDIR=/data/ShellCrash
INIT=/etc/init.d/shellcrash_d01
HOOK=/data/shellcrash_firewall_hook.sh
S95=/etc/rc.d/S95shellcrash_d01
K10=/etc/rc.d/K10shellcrash_d01
AUTO=/data/auto_start.sh

clear_snapshot() {
    for f in boot_snapshot_ready boot_snapshot_ready.new prev_init prev_init_present prev_hook prev_hook_present prev_auto prev_auto_present prev_s95_file prev_s95_link prev_k10_file prev_k10_link prev_uci_present prev_uci_type prev_uci_option_type prev_uci_option_type_present prev_uci_path prev_uci_path_present prev_uci_enabled prev_uci_enabled_present; do
        rm -f "$TX/$f"
    done
}

snapshot_file() {
    source_path=$1
    backup_name=$2
    present_name=$3
    if [ -f "$source_path" ]; then
        cp -p "$source_path" "$TX/$backup_name" || return 1
        : >"$TX/$present_name" || return 1
    fi
}

snapshot_link_or_file() {
    source_path=$1
    file_name=$2
    link_name=$3
    if [ -L "$source_path" ]; then
        command -v readlink >/dev/null 2>&1 || return 1
        readlink "$source_path" >"$TX/$link_name" || return 1
    elif [ -f "$source_path" ]; then
        cp -p "$source_path" "$TX/$file_name" || return 1
    fi
}

restore_link_or_file() {
    target_path=$1
    file_name=$2
    link_name=$3
    rm -f "$target_path" || return 1
    if [ -s "$TX/$link_name" ]; then
        link_target=$(cat "$TX/$link_name" 2>/dev/null)
        case "$link_target" in ../init.d/*|/etc/init.d/*) ;; *) return 1;; esac
        ln -s "$link_target" "$target_path" || return 1
    elif [ -f "$TX/$file_name" ]; then
        cp -p "$TX/$file_name" "$target_path" || return 1
    fi
}

[ -n "$TOKEN" ] || exit 1
[ "$(cat "$TX/owner" 2>/dev/null)" = "$TOKEN" ] || exit 1

case "$ACTION" in
snapshot)
    clear_snapshot
    snapshot_file "$INIT" prev_init prev_init_present || exit 1
    snapshot_file "$HOOK" prev_hook prev_hook_present || exit 1
    snapshot_file "$AUTO" prev_auto prev_auto_present || exit 1
    snapshot_link_or_file "$S95" prev_s95_file prev_s95_link || exit 1
    snapshot_link_or_file "$K10" prev_k10_file prev_k10_link || exit 1
    if uci -q get firewall.ShellCrash >/dev/null 2>&1; then
        : >"$TX/prev_uci_present" || exit 1
        uci -q get firewall.ShellCrash >"$TX/prev_uci_type" 2>/dev/null || exit 1
        if uci -q get firewall.ShellCrash.type >"$TX/prev_uci_option_type" 2>/dev/null; then
            : >"$TX/prev_uci_option_type_present" || exit 1
        else
            rm -f "$TX/prev_uci_option_type"
        fi
        if uci -q get firewall.ShellCrash.path >"$TX/prev_uci_path" 2>/dev/null; then
            : >"$TX/prev_uci_path_present" || exit 1
        else
            rm -f "$TX/prev_uci_path"
        fi
        if uci -q get firewall.ShellCrash.enabled >"$TX/prev_uci_enabled" 2>/dev/null; then
            : >"$TX/prev_uci_enabled_present" || exit 1
        else
            rm -f "$TX/prev_uci_enabled"
        fi
    fi
    printf '%s\n' "$TOKEN" >"$TX/boot_snapshot_ready.new" && mv -f "$TX/boot_snapshot_ready.new" "$TX/boot_snapshot_ready" || exit 1
    echo BOOT_PERSISTENT_STATE_SNAPSHOTTED
    ;;
rollback)
    [ "$(cat "$TX/boot_snapshot_ready" 2>/dev/null)" = "$TOKEN" ] || exit 1
    [ "$(cat "$TX/mutation" 2>/dev/null)" = "$TOKEN" ] || exit 1
    touch "$CRASHDIR/.dis_startup" || exit 1
    if [ -x "$INIT" ]; then
        "$INIT" stop >/tmp/d01-boot-transaction-stop.log 2>&1 || true
    fi
    if [ -r "$CRASHDIR/libs/get_config.sh" ] && [ -x "$CRASHDIR/starts/fw_stop.sh" ]; then
        ( export CRASHDIR; . "$CRASHDIR/libs/get_config.sh"; . "$CRASHDIR/starts/fw_stop.sh" ) >>/tmp/d01-boot-transaction-stop.log 2>&1 || true
    fi
    for pid in $(pidof CrashCore 2>/dev/null); do
        saved_start=$(awk '{print $22; exit}' "/proc/$pid/stat" 2>/dev/null)
        current_start=$(awk '{print $22; exit}' "/proc/$pid/stat" 2>/dev/null)
        [ -n "$saved_start" ] && [ "$current_start" = "$saved_start" ] && \
            [ "$(cat "/proc/$pid/comm" 2>/dev/null)" = CrashCore ] && kill "$pid" 2>/dev/null
    done
    sleep 2
    command -v iptables-save >/dev/null 2>&1 || exit 1
    rules=$(iptables-save 2>/dev/null) || exit 1
    refs=$(printf '%s\n' "$rules" | grep -Eic 'shellcrash|clash|mihomo' || true)
    ! pidof CrashCore >/dev/null 2>&1 || exit 1
    [ "${refs:-0}" -eq 0 ] || exit 1
    [ -f "$CRASHDIR/.dis_startup" ] || exit 1

    if [ -f "$TX/prev_init_present" ]; then cp -p "$TX/prev_init" "$INIT" || exit 1; else rm -f "$INIT" || exit 1; fi
    if [ -f "$TX/prev_hook_present" ]; then cp -p "$TX/prev_hook" "$HOOK" || exit 1; else rm -f "$HOOK" || exit 1; fi
    if [ -f "$TX/prev_auto_present" ]; then cp -p "$TX/prev_auto" "$AUTO" || exit 1; else rm -f "$AUTO" || exit 1; fi
    restore_link_or_file "$S95" prev_s95_file prev_s95_link || exit 1
    restore_link_or_file "$K10" prev_k10_file prev_k10_link || exit 1

    uci -q delete firewall.ShellCrash >/dev/null 2>&1 || true
    if [ -f "$TX/prev_uci_present" ]; then
        uci_type=$(cat "$TX/prev_uci_type" 2>/dev/null)
        case "$uci_type" in ''|*[!A-Za-z0-9_]*) exit 1;; esac
        uci set "firewall.ShellCrash=$uci_type" || exit 1
        if [ -f "$TX/prev_uci_option_type_present" ]; then
            uci_option_type=$(cat "$TX/prev_uci_option_type" 2>/dev/null)
            uci set "firewall.ShellCrash.type=$uci_option_type" || exit 1
        fi
        if [ -f "$TX/prev_uci_path_present" ]; then
            uci_path=$(cat "$TX/prev_uci_path" 2>/dev/null)
            uci set "firewall.ShellCrash.path=$uci_path" || exit 1
        fi
        if [ -f "$TX/prev_uci_enabled_present" ]; then
            uci_enabled=$(cat "$TX/prev_uci_enabled" 2>/dev/null)
            uci set "firewall.ShellCrash.enabled=$uci_enabled" || exit 1
        fi
    fi
    uci commit firewall || exit 1
    echo BOOT_TRANSACTION_ROLLBACK_CONFIRMED
    ;;
*)
    exit 1
    ;;
esac
