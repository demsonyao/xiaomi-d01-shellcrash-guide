#!/bin/sh

CRASHDIR=/data/ShellCrash
[ -f "$CRASHDIR/.dis_startup" ] && exit 0
pidof CrashCore >/dev/null 2>&1 || exit 0

. "$CRASHDIR/libs/get_config.sh"
. "$CRASHDIR/starts/fw_start.sh"
chmod 0600 /tmp/ShellCrash/config.yaml 2>/dev/null || exit 1

# D01 names its WAN-facing interface eth0.  Insert explicit service blocks
# before ShellCrash's source-based accepts so router administration and the
# controller remain LAN-only even behind an upstream private router.
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
exit 0
