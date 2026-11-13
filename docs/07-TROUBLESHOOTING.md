# 故障排查与安全回滚

## 安全停止并恢复直连

在路由器 SSH 中：

```sh
touch /data/ShellCrash/.dis_startup
/etc/init.d/shellcrash_d01 stop

CRASHDIR=/data/ShellCrash
export CRASHDIR
. "$CRASHDIR/libs/get_config.sh"
. "$CRASHDIR/starts/fw_stop.sh"
```

确认：

```sh
pidof CrashCore || echo CORE_STOPPED
iptables-save 2>/dev/null | grep -Eic 'shellcrash|clash|mihomo'
```

规则数量应为 `0`。如果 SSH 已断但路由管理页仍可开，先等待脚本设置的 180 秒（启动/防火墙）或 300 秒（boot）watchdog；仍未恢复再重启路由。

## 常见现象

| 现象 | 原因与处理 |
|---|---|
| 路由管理页可开但 SSH 不通 | Web 与 Dropbear 是两项服务；按 SSH 章节运行 `enable_ssh_d01.py --mode recover-existing` |
| 首次流程只开了 Telnet 23 | 原流程在 D01 读不到 `/etc/openwrt_release`；应用 gateway ARMv7 回退补丁 |
| 重启后 SSH 消失 | 通用 procd 启动文件不适配 D01 legacy init；运行 `repair_d01_dropbear_boot.py` |
| `can't open '/starts/fw_getlanip.sh'` | 调用防火墙脚本前未导出 `CRASHDIR=/data/ShellCrash` |
| API 返回 401 | Controller secret 已启用，是本教程监听 `:9999` 时的必需健康状态 |
| API 返回 200 | Controller 未要求认证；停止启用防火墙，重新运行运行时准备并设置 secret |
| 配置测试显示 `Killed` | 内存不足；停止主核心和透明规则，仅运行候选核心做离线校验 |
| 核心启动但启用规则后断网 | 主策略没有可用节点；先在防火墙前完成延迟测试和选择 |
| Trojan 全部 503 | 先检查完整 YAML、节点 DNS 和握手；不要直接归因于 UPX |
| X/Facebook DNS SERVFAIL | 境外 DoH 被直连阻断；使用 `https://...#策略组` |
| TUN 开关打不开 | D01 内核没有 TUN 设备/模块，属于能力限制 |
| TPROXY 帮助存在但规则失败 | 用户态有帮助，内核 target 未注册 |
| 重启后 `/tmp/ShellCrash/config.yaml` 不见 | `/tmp` 本来就是易失目录；应由启动流程重建 |
| `fw_start` 返回 1 | 不能仅凭返回码判断；检查实际规则、Controller API 和客户端严格 204；面板仅在已安装时检查 |
| `TRANSACTION_RETRY_REFUSED_*` | 上一轮共享安全事务仍在运行或保留了失败现场；不要删事务目录或盲目 kill，先确认当前核心、规则与 `/tmp/d01-shellcrash-transaction` |
| 路由数小时后变慢 | 保存监控快照，检查 MemAvailable、slab、FD、conntrack 和核心 RSS；不要直接重装 |
| v1.19.29 升级空间不足 | 切换需同时保留新旧核心和回滚空间；当前恢复基线仍为 v1.19.28 |

## DNS 专项诊断

```powershell
.\run.bat diagnose_d01_x_facebook.py
```

```bash
./run.sh diagnose_d01_x_facebook.py
```

它区分：

- 客户端经路由 DNS；
- 客户端透明 TCP；
- Mihomo DNS API；
- 路由本机直连 DoH；
- 路由显式经 Mihomo TCP。

不要在公开日志中附带完整配置或 Controller secret。

## 稳定性监控

```powershell
.\run.bat install_d01_stability_monitor.py
```

```bash
./run.sh install_d01_stability_monitor.py
```

监控器不自启、不改路由，只在当前开机周期采集轻量指标。受控启动、防火墙和 boot 测试会短暂设置 maintenance 标志，避免把计划内变更误判成故障。触发快照：

```text
/data/d01-stability/last-trigger.txt
```

环形采样：

```text
/tmp/d01-stability/ring.0.csv
```

重启会清空 `/tmp` 采样，但持久触发快照保留。

只读确认它目前是否仍在运行：

```powershell
.\run.bat check_d01_stability_monitor.py
```

```bash
./run.sh check_d01_stability_monitor.py
```

`MONITOR_RUNNING_PID=...` 才代表正在采样；`MONITOR_FILE=YES` 与 `MONITOR_NOT_RUNNING` 同时出现，表示重装后脚本仍在，但当前没有探针进程。

## 不要做的事

- 不要在不确认分区的情况下 `mtd write`；
- 不要删除整个 `/data`；
- 不要把面板“能点开”当成 TUN/TPROXY 可用；
- 不要在透明规则已接管 LAN 时试验未知配置而没有 failsafe；
- 不要把故障归档上传到网盘或公开 issue。
