#!/bin/sh

CRASHDIR=/data/ShellCrash
CFG_PATH="$CRASHDIR/configs/ShellCrash.cfg"
. "$CRASHDIR/libs/set_config.sh"

setconfig versionsh_l 1.9.4release
setconfig release_type stable
setconfig update_url https://testingcf.jsdelivr.net/gh/juewuy/ShellCrash@stable
setconfig userguide 1
setconfig cpucore armv7
setconfig crashcore meta
setconfig zip_type upx
setconfig redir_mod 'Redir模式'
# D01 stock firmware has no TUN/TPROXY kernel path. In Redir mode, using
# real DNS answers keeps un-intercepted game UDP traffic routable directly.
setconfig dns_mod redir_host
setconfig firewall_mod iptables
setconfig firewall_area 1
setconfig cust_host_ipv4 192.168.31.0/24
setconfig replace_default_host_ipv4 ON
setconfig fw_wan ON
setconfig cn_ip_route OFF
setconfig ipv6_redir OFF
setconfig ipv6_support OFF
setconfig ipv6_dns OFF
setconfig common_ports ON
setconfig start_old ON

# Keep boot activation disabled until the first controlled start succeeds.
touch "$CRASHDIR/.dis_startup"

if [ -s /tmp/.shellcrash_subscription_url ]; then
    subscription_url=$(cat /tmp/.shellcrash_subscription_url)
    case "$subscription_url" in
        *"'"* | *"\n"* | *"\r"*) exit 2 ;;
    esac
    setconfig Https "'$subscription_url'"
else
    # A local file has no safe refresh URL. Keep automatic subscription updates off.
    setconfig Https
fi
setconfig Url
rm -f /tmp/.shellcrash_subscription_url
