#!/bin/sh /etc/rc.common

START=95
STOP=10
EXTRA_COMMANDS="test_start"

CRASHDIR=/data/ShellCrash

harden_input() {
    iptables -C INPUT -i eth0 -p tcp -m multiport --dports 22,80,443,7890,9999 -j REJECT >/dev/null 2>&1 || \
        iptables -I INPUT 1 -i eth0 -p tcp -m multiport --dports 22,80,443,7890,9999 -j REJECT
    iptables -C INPUT -i eth0 -p udp -m multiport --dports 7890,9999 -j REJECT >/dev/null 2>&1 || \
        iptables -I INPUT 1 -i eth0 -p udp -m multiport --dports 7890,9999 -j REJECT
    if command -v ip6tables >/dev/null 2>&1; then
        ip6tables -C INPUT -i eth0 -p tcp -m multiport --dports 22,80,443,7890,9999 -j REJECT >/dev/null 2>&1 || \
            ip6tables -I INPUT 1 -i eth0 -p tcp -m multiport --dports 22,80,443,7890,9999 -j REJECT
        ip6tables -C INPUT -i eth0 -p udp -m multiport --dports 7890,9999 -j REJECT >/dev/null 2>&1 || \
            ip6tables -I INPUT 1 -i eth0 -p udp -m multiport --dports 7890,9999 -j REJECT
    fi
}

test_start() {
    [ -x "$CRASHDIR/start.sh" ] || return 1
    pidof CrashCore >/dev/null 2>&1 && return 0
    "$CRASHDIR/start.sh" start || return 1
    chmod 0600 /tmp/ShellCrash/config.yaml 2>/dev/null || return 1
    harden_input
}

start() {
    [ -f "$CRASHDIR/.dis_startup" ] && return 0
    test_start
}

stop() {
    [ -x "$CRASHDIR/start.sh" ] || return 0
    "$CRASHDIR/start.sh" stop
}

restart() {
    stop
    sleep 2
    start
}

status() {
    pidof CrashCore >/dev/null 2>&1
}
