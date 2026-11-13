# 自启、重启和最终验收

## 重启前只读检查

```powershell
.\run.bat verify_d01_install.py
```

```bash
./run.sh verify_d01_install.py
```

期望：

```text
CORE=RUNNING
CONTROLLER_API_HTTP=401
TCP_REDIR=YES
TPROXY_RULES=0
SHELLCRASH_MANGLE_REFS=0
DNS_MODE=redir_host
DNS_LISTEN=:1053
UDP_POLICY=DIRECT_VERIFIED
AUTOSTART_LOCK=OFF
D01_VERIFY_OK
```

若安装了 Zashboard，另应看到 `DASHBOARD_OPTIONAL_STATUS=READY`；未安装时显示 `NOT_INSTALLED`，不影响核心验收。若出现 `NOT_READY` 或 `PARTIAL`，核心/路由验收仍可通过，但面板本身需要另行排查；`PARTIAL` 表示 `ui/index.html`、`ui/manifest.webmanifest`、JavaScript 资产或目录内容不完整。新版官方 Release 不再保证包含 `CNAME`。

同时确认：

- `http://192.168.31.1` 正常；
- 若安装了 Zashboard，`http://192.168.31.1:9999/ui/` 正常；
- 至少一个 TCP 站点按规则代理；
- 游戏或其他目标 UDP 正常直连；
- X/Facebook 等目标域名 DNS 有答案；
- 没有 WAN 端口映射到 22、7890 或 9999。

## 重启

在路由器 SSH 中：

```sh
sync
reboot
```

等待 Mesh 和 Wi-Fi 完整恢复后重新运行：

```powershell
.\run.bat verify_d01_install.py
```

```bash
./run.sh verify_d01_install.py
```

并测试 SSH：

```powershell
ssh root@192.168.31.1
```

重启后 `/tmp/ShellCrash` 会重新生成，这属于正常行为。持久配置位于 `/data/ShellCrash`。

## 可选稳定性探针

探针文件位于 `/data/d01-stability/monitor.sh`，不属于 `/data/ShellCrash`，因此重装 ShellCrash 不会删除它。它默认**不设开机自启**：路由器一旦重启，探针进程和 `/tmp/d01-stability/` 的环形采样都会消失；如果曾触发异常，`/data/d01-stability/last-trigger.txt` 会持久保留。

只读检查（不会启动、停止或修改探针）：

```powershell
.\run.bat check_d01_stability_monitor.py
```

```bash
./run.sh check_d01_stability_monitor.py
```

结果判读：

- `MONITOR_FILE=YES` + `MONITOR_RUNNING_PID=...`：仍在采样；
- `MONITOR_FILE=YES` + `MONITOR_NOT_RUNNING`：脚本还在，但进程已停止，最常见原因是路由器重启；
- `RUNTIME_RING0=YES`：本次开机周期仍有采样；
- `PERSISTENT_TRIGGER_SNAPSHOT=YES`：曾写下持久异常快照；该文件可能含设备和网络细节，不要公开上传。

若 `trigger_reason=core_process_count_abnormal` 的时间正好落在这次受控重装/停核窗口，它可能只是计划内维护被探针记录，并不等同于内存泄漏。探针仍在运行时，后续采样会继续，但每个开机周期默认只持久化第一份触发快照。

## 在路由 Shell 中可看的内容

```sh
ls -lah /data/ShellCrash
ls -lah /data/ShellCrash/yamls
sed -n '1,120p' /data/ShellCrash/yamls/user.yaml
grep -E '^(core_v|redir_mod|dns_mod|firewall_mod|firewall_area|ipv6_redir)=' \
  /data/ShellCrash/configs/ShellCrash.cfg
pidof CrashCore
iptables-save | grep -Ei 'shellcrash|clash|mihomo'
```

不要把命令输出原样贴到公开 issue；其中可能包含节点、secret 或设备标识。

## ShellCrash 菜单哪些可以动

日常可安全操作：

- 选择策略组/节点；
- 查看连接与日志；
- 手动更新规则后做一次受控验证；
- 停止/启动服务。

本方案中不要改：

- Redir → TUN/TProxy；
- redir-host → Fake-IP；
- IPv6 透明代理；
- D01 legacy 启动方式；
- LAN 自定义网段，除非你的真实 LAN 已改变。

“过滤非常用端口”“过滤 QUIC”“过滤 CN_IP”都不是本教程成功的必要条件。不了解影响时保持当前值。

## 封存最终私人快照

重启验收通过后，立即运行 [最终应用快照](02-BACKUP.md#最终应用快照)。导出器会同时记录防火墙 UCI 与四个 rc 链接；只有这一步完成后，私人恢复包才拥有当前成功状态的应用金本。完整重装仍依赖另行固定的离线资产和 XMiR 基线。
