#!/bin/sh

BASE=/data/d01-stability
RUNDIR=/tmp/d01-stability
PIDFILE="$RUNDIR/monitor.pid"
RING0="$RUNDIR/ring.0.csv"
RING1="$RUNDIR/ring.1.csv"
TRIGGERED="$RUNDIR/triggered"
MAINTENANCE="$RUNDIR/maintenance"
INTERVAL=60
ROTATE_LINES=90
SNAPSHOT_MAX=196608
HEADER='epoch,time,maintenance,mem_available_kb,slab_kb,sreclaimable_kb,sunreclaim_kb,load1,core_count,core_rss_kb,core_threads,core_fds,conntrack_count,conntrack_max,conntrack_pct,sockets_used,tcp_inuse,udp_inuse,api_http,api_seconds,firewall_refs,kernel_evidence'

mem_value() {
    awk -v key="$1:" '$1 == key {print $2; exit}' /proc/meminfo 2>/dev/null
}

proc_value() {
    awk -v key="$2:" '$1 == key {print $2; exit}' "/proc/$1/status" 2>/dev/null
}

socket_value() {
    awk -v family="$1:" -v field="$2" '
        $1 == family {for (i=2; i<=NF; i++) if ($i == field) {print $(i+1); exit}}
    ' /proc/net/sockstat 2>/dev/null
}

write_header() {
    [ -s "$RING0" ] || printf '%s\n' "$HEADER" >"$RING0"
}

rotate_ring() {
    lines=$(wc -l <"$RING0" 2>/dev/null)
    [ -z "$lines" ] && lines=0
    if [ "$lines" -gt "$ROTATE_LINES" ]; then
        mv -f "$RING0" "$RING1"
        printf '%s\n' "$HEADER" >"$RING0"
    fi
}

snapshot() {
    reason="$1"
    [ -f "$TRIGGERED" ] && return 0
    : >"$TRIGGERED"
    tmp="$RUNDIR/snapshot.$$"
    {
        echo 'D01_STABILITY_TRIGGER_V1'
        echo "trigger_reason=$reason"
        echo "trigger_time=$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null)"
        echo
        echo '=== RECENT_SAMPLES ==='
        [ -s "$RING1" ] && cat "$RING1"
        [ -s "$RING0" ] && cat "$RING0"
        echo
        echo '=== MEMINFO ==='
        cat /proc/meminfo 2>/dev/null
        echo
        echo '=== LOAD_AND_SOCKETS ==='
        cat /proc/loadavg /proc/net/sockstat 2>/dev/null
        echo
        echo '=== CORE_STATUS ==='
        for pid in $(pidof CrashCore 2>/dev/null); do
            echo "pid=$pid fd_count=$(ls "/proc/$pid/fd" 2>/dev/null | wc -l)"
            cat "/proc/$pid/status" "/proc/$pid/limits" 2>/dev/null
        done
        echo
        echo '=== CONNTRACK ==='
        cat /proc/sys/net/netfilter/nf_conntrack_count \
            /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null
        echo
        echo '=== SERVICE_COUNTS ==='
        printf 'api_http='
        curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
            http://127.0.0.1:9999/version 2>/dev/null
        echo
        printf 'shellcrash_firewall_refs='
        iptables-save 2>/dev/null | grep -Eic 'shellcrash|clash|mihomo'
        echo
        echo '=== DMESG_TAIL ==='
        dmesg 2>/dev/null | tail -n 250
        echo
        echo '=== LOGREAD_TAIL ==='
        logread 2>/dev/null | tail -n 200
        echo
        echo '=== FILESYSTEM ==='
        df -h /data /tmp 2>&1
    } >"$tmp"
    size=$(wc -c <"$tmp" 2>/dev/null)
    [ -z "$size" ] && size=0
    if [ "$size" -gt "$SNAPSHOT_MAX" ]; then
        {
            head -n 20 "$tmp"
            echo '=== SNAPSHOT_TRUNCATED_TO_LAST_180KB ==='
            tail -c 184320 "$tmp"
        } >"$tmp.capped"
        mv -f "$tmp.capped" "$tmp"
    fi
    mkdir -p "$BASE"
    chmod 0700 "$BASE"
    mv -f "$tmp" "$BASE/last-trigger.txt"
    chmod 0600 "$BASE/last-trigger.txt"
    sync
}

status_monitor() {
    if [ -s "$PIDFILE" ]; then
        pid=$(cat "$PIDFILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "MONITOR_RUNNING_PID=$pid"
            [ -s "$RING0" ] && tail -n 2 "$RING0"
            [ -s "$BASE/last-trigger.txt" ] && echo 'PERSISTENT_TRIGGER_SNAPSHOT=YES' || \
                echo 'PERSISTENT_TRIGGER_SNAPSHOT=NO'
            return 0
        fi
    fi
    echo MONITOR_NOT_RUNNING
    return 1
}

run_monitor() {
    mkdir -p "$RUNDIR" "$BASE"
    chmod 0700 "$RUNDIR" "$BASE"
    echo $$ >"$PIDFILE"
    chmod 0600 "$PIDFILE"
    trap 'rm -f "$PIDFILE"' EXIT
    trap 'exit 0' INT TERM
    write_header

    cpu_count=$(grep -c '^processor' /proc/cpuinfo 2>/dev/null)
    [ -z "$cpu_count" ] || [ "$cpu_count" -lt 1 ] && cpu_count=1
    load_limit=$((cpu_count * 2))
    sample_no=0
    base_count=0
    base_mem_sum=0
    base_rss_sum=0
    base_sun_sum=0
    base_threads_sum=0
    base_fds_sum=0
    base_mem=0
    base_rss=0
    base_sun=0
    base_threads=0
    base_fds=0
    soft_count=0
    last_refs=0
    last_evidence=0
    last_pid=

    while :; do
        sample_no=$((sample_no + 1))
        epoch=$(date +%s 2>/dev/null)
        iso=$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null)
        [ -z "$epoch" ] && epoch=0

        maintenance=0
        if [ -s "$MAINTENANCE" ]; then
            maintenance_epoch=$(cat "$MAINTENANCE" 2>/dev/null)
            [ -z "$maintenance_epoch" ] && maintenance_epoch=$epoch
            maintenance_age=$((epoch - maintenance_epoch))
            if [ "$maintenance_age" -ge 0 ] && [ "$maintenance_age" -lt 900 ]; then
                maintenance=1
            else
                rm -f "$MAINTENANCE"
            fi
        fi

        mem_available=$(mem_value MemAvailable)
        slab=$(mem_value Slab)
        sreclaim=$(mem_value SReclaimable)
        sunreclaim=$(mem_value SUnreclaim)
        [ -z "$mem_available" ] && mem_available=0
        [ -z "$slab" ] && slab=0
        [ -z "$sreclaim" ] && sreclaim=0
        [ -z "$sunreclaim" ] && sunreclaim=0
        load1=$(awk '{print $1}' /proc/loadavg 2>/dev/null)
        [ -z "$load1" ] && load1=0

        pids=$(pidof CrashCore 2>/dev/null)
        core_count=0
        core_rss=0
        core_threads=0
        core_fds=0
        first_pid=
        for pid in $pids; do
            case "$pid" in *[!0-9]*|'') continue;; esac
            [ -z "$first_pid" ] && first_pid=$pid
            core_count=$((core_count + 1))
            value=$(proc_value "$pid" VmRSS); [ -z "$value" ] && value=0
            core_rss=$((core_rss + value))
            value=$(proc_value "$pid" Threads); [ -z "$value" ] && value=0
            core_threads=$((core_threads + value))
            value=$(ls "/proc/$pid/fd" 2>/dev/null | wc -l); [ -z "$value" ] && value=0
            core_fds=$((core_fds + value))
        done

        ct_count=$(cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null)
        ct_max=$(cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null)
        [ -z "$ct_count" ] && ct_count=0
        [ -z "$ct_max" ] || [ "$ct_max" -lt 1 ] && ct_max=1
        ct_pct=$((ct_count * 100 / ct_max))
        sockets_used=$(socket_value sockets used); [ -z "$sockets_used" ] && sockets_used=0
        tcp_inuse=$(socket_value TCP inuse); [ -z "$tcp_inuse" ] && tcp_inuse=0
        udp_inuse=$(socket_value UDP inuse); [ -z "$udp_inuse" ] && udp_inuse=0

        api_start=$(date +%s 2>/dev/null); [ -z "$api_start" ] && api_start=$epoch
        if [ "$core_count" -gt 0 ]; then
            api_http=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 \
                http://127.0.0.1:9999/version 2>/dev/null)
        else
            api_http=000
        fi
        [ -z "$api_http" ] && api_http=000
        api_end=$(date +%s 2>/dev/null); [ -z "$api_end" ] && api_end=$api_start
        api_seconds=$((api_end - api_start))

        if [ $((sample_no % 5)) -eq 1 ]; then
            last_refs=$(iptables-save 2>/dev/null | grep -Eic 'shellcrash|clash|mihomo')
            last_evidence=$(dmesg 2>/dev/null | grep -Eic \
                'out of memory|oom-killer|killed process|nf_conntrack.*table full')
        fi
        [ -z "$last_refs" ] && last_refs=0
        [ -z "$last_evidence" ] && last_evidence=0

        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
            "$epoch" "$iso" "$maintenance" "$mem_available" "$slab" "$sreclaim" \
            "$sunreclaim" "$load1" "$core_count" "$core_rss" "$core_threads" \
            "$core_fds" "$ct_count" "$ct_max" "$ct_pct" "$sockets_used" \
            "$tcp_inuse" "$udp_inuse" "$api_http" "$api_seconds" "$last_refs" \
            "$last_evidence" >>"$RING0"
        rotate_ring

        if [ "$maintenance" -eq 0 ] && [ "$core_count" -eq 1 ] && \
            [ "$api_http" = 401 ] && [ "$last_refs" -gt 0 ] && \
            [ "$base_count" -lt 10 ]; then
            base_count=$((base_count + 1))
            base_mem_sum=$((base_mem_sum + mem_available))
            base_rss_sum=$((base_rss_sum + core_rss))
            base_sun_sum=$((base_sun_sum + sunreclaim))
            base_threads_sum=$((base_threads_sum + core_threads))
            base_fds_sum=$((base_fds_sum + core_fds))
            if [ "$base_count" -eq 10 ]; then
                base_mem=$((base_mem_sum / 10))
                base_rss=$((base_rss_sum / 10))
                base_sun=$((base_sun_sum / 10))
                base_threads=$((base_threads_sum / 10))
                base_fds=$((base_fds_sum / 10))
                printf 'mem_kb=%s rss_kb=%s sunreclaim_kb=%s threads=%s fds=%s\n' \
                    "$base_mem" "$base_rss" "$base_sun" "$base_threads" "$base_fds" \
                    >"$RUNDIR/baseline.txt"
            fi
        fi

        reason=
        soft_reason=
        if [ "$maintenance" -eq 0 ]; then
            [ "$mem_available" -lt 8192 ] && reason=mem_available_below_8mb
            [ "$ct_pct" -ge 95 ] && reason=conntrack_above_95pct
            [ "$last_evidence" -gt 0 ] && reason=kernel_oom_or_conntrack_evidence
            [ "$core_count" -ne 1 ] && soft_reason=core_process_count_abnormal
            case "$api_http" in 401) ;; *) soft_reason=controller_api_unhealthy_or_unauthenticated;; esac
            [ "$last_refs" -eq 0 ] && soft_reason=firewall_rules_missing
            [ "$mem_available" -lt 16384 ] && soft_reason=mem_available_below_16mb
            [ "$ct_pct" -ge 85 ] && soft_reason=conntrack_above_85pct
            awk -v load="$load1" -v limit="$load_limit" 'BEGIN {exit !(load > limit)}' && \
                soft_reason=load_above_twice_cpu_count
            if [ "$base_count" -ge 10 ]; then
                rss_limit=$((base_rss + 32768)); [ "$rss_limit" -lt 98304 ] && rss_limit=98304
                sun_limit=$((base_sun + 16384)); [ "$sun_limit" -lt 32768 ] && sun_limit=32768
                thread_limit=$((base_threads + 64)); [ "$thread_limit" -lt 128 ] && thread_limit=128
                fd_limit=$((base_fds + 512)); [ "$fd_limit" -lt 1024 ] && fd_limit=1024
                [ "$core_rss" -gt "$rss_limit" ] && soft_reason=core_rss_growth
                [ "$sunreclaim" -gt "$sun_limit" ] && [ "$mem_available" -lt 24576 ] && \
                    soft_reason=kernel_sunreclaim_growth
                [ "$core_threads" -gt "$thread_limit" ] && soft_reason=core_thread_growth
                [ "$core_fds" -gt "$fd_limit" ] && soft_reason=core_fd_growth
                [ -n "$last_pid" ] && [ -n "$first_pid" ] && [ "$last_pid" != "$first_pid" ] && \
                    soft_reason=core_pid_changed
            fi
        fi

        if [ -n "$reason" ]; then
            snapshot "$reason"
            soft_count=0
        elif [ -n "$soft_reason" ]; then
            soft_count=$((soft_count + 1))
            [ "$soft_count" -ge 3 ] && snapshot "$soft_reason"
        else
            soft_count=0
        fi
        last_pid=$first_pid
        sleep "$INTERVAL"
    done
}

case "$1" in
    run) run_monitor ;;
    status) status_monitor ;;
    *) echo 'Usage: monitor.sh {run|status}'; exit 2 ;;
esac
