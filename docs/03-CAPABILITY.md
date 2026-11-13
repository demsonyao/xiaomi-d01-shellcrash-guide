# 确认 D01 的 TUN/TPROXY 能力

运行临时链探测：

```powershell
.\run.bat probe_d01_tproxy_capability.py
```

```bash
./run.sh probe_d01_tproxy_capability.py
```

它会在 IPv4 `mangle` 表创建一个随机唯一、**不挂入 PREROUTING/OUTPUT 等数据路径**的临时链，尝试插入一条 TPROXY 规则后立即删除。脚本先拒绝同名碰撞，并且只清理由本次运行写入 marker 的链。它会短暂修改防火墙表，因此不是纯只读；测试期间不会接管实际流量。

在 D01 1.0.72 的实测结果：

```text
KERNEL=3.14.77
TUN_DEVICE=NO
TPROXY_HELP=YES
TPROXY_REGISTERED=NO
TPROXY_MODULE_FILES=0
MODPROBE=NO
RULE_INSERT_RC=1
TPROXY_KERNEL_RULE_TEST=UNSUPPORTED
PROBE_CHAIN_REMOVED_NO_TRAFFIC_HOOKS_CHANGED
```

`iptables -j TPROXY -h` 能显示帮助，只说明用户态 iptables 认识语法；真正插入规则时报 `No chain/target/match by that name`，说明内核 target 没有注册。

本教程因此固定使用：

```text
redir_mod=Redir模式
dns_mod=redir_host
firewall_mod=iptables
firewall_area=1
ipv6_redir=OFF
```

设计结果：

- TCP 可透明分流；
- DNS 返回真实 IP；
- UDP 直接由路由 NAT；
- 游戏不依赖 Fake-IP 映射；
- UDP 不享受 Mihomo 规则和代理隐私；
- TUN 面板开关应保持关闭。
