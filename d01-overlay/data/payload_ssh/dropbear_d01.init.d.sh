#!/bin/sh /etc/rc.common

START=19
STOP=50

PROG=/etc/crontabs/dropbearmulti/dropbear
PIDFILE=/var/run/dropbear.pid
KEYDIR=/etc/dropbear

start() {
    [ -x "$PROG" ] || return 1
    mkdir -p "$KEYDIR"
    chmod 0700 "$KEYDIR"

    [ -s "$KEYDIR/dropbear_ed25519_host_key" ] || \
        "$PROG" dropbearkey -t ed25519 -f "$KEYDIR/dropbear_ed25519_host_key"
    [ -s "$KEYDIR/dropbear_ecdsa_host_key" ] || \
        "$PROG" dropbearkey -t ecdsa -f "$KEYDIR/dropbear_ecdsa_host_key"

    "$PROG" -P "$PIDFILE" -p 22
}

stop() {
    if [ -s "$PIDFILE" ]; then
        kill "$(cat "$PIDFILE")" 2>/dev/null
        rm -f "$PIDFILE"
    else
        killall dropbear 2>/dev/null
    fi
}

restart() {
    stop
    sleep 1
    start
}
