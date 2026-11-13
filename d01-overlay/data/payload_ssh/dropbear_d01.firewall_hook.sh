#!/bin/sh

XDIR=/etc/crontabs/dropbearmulti
PROG="$XDIR/dropbear"
SOURCE_INIT="$XDIR/init.d01.sh"
TARGET_INIT=/etc/init.d/dropbear
PIDFILE=/var/run/dropbear.pid
KEYDIR=/etc/dropbear

[ -x "$PROG" ] || exit 1

# A generic XMiR firewall installer uses a procd init script.  D01 runs the
# legacy Xiaomi init, so restore the D01-compatible service if it was replaced.
if [ -s "$SOURCE_INIT" ]; then
    if ! cmp -s "$SOURCE_INIT" "$TARGET_INIT" 2>/dev/null; then
        cp -f "$SOURCE_INIT" "$TARGET_INIT"
        chmod 0755 "$TARGET_INIT"
    fi
fi

pidof dropbear >/dev/null 2>&1 && exit 0

if [ -x "$TARGET_INIT" ]; then
    "$TARGET_INIT" start >/tmp/dropbear_d01_hook_start.log 2>&1
fi

pidof dropbear >/dev/null 2>&1 && exit 0

mkdir -p "$KEYDIR"
chmod 0700 "$KEYDIR"
[ -s "$KEYDIR/dropbear_ed25519_host_key" ] || \
    "$PROG" dropbearkey -t ed25519 -f "$KEYDIR/dropbear_ed25519_host_key" >/dev/null 2>&1
[ -s "$KEYDIR/dropbear_ecdsa_host_key" ] || \
    "$PROG" dropbearkey -t ecdsa -f "$KEYDIR/dropbear_ecdsa_host_key" >/dev/null 2>&1

"$PROG" -P "$PIDFILE" -p 22 >/tmp/dropbear_d01_hook_direct.log 2>&1
exit 0
