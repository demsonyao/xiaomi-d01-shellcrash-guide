# 完整文件清单与分类

本清单记录这次研究产生或使用的相关文件。它不是“全部都应发布”的清单。

## 验证状态

- 目标机成功链已实测：SSH 恢复/持久化、框架/核心/面板、legacy 启动、iptables TCP Redir、redir-host、UDP 直连、DNS 修复和重启恢复；
- 公开参数化脚本已通过 Python 语法、Shell 行尾、公开内容和 ZIP 逐文件审计；
- 公开包装器尚待恢复出厂后的完整复演，Linux/macOS 启动路径也尚待实机复演；
- `capture_broken_shellcrash_d01.py` 和监控器在目标机运行过，但它们的输出始终属于私人材料。

## A. 公开主流程

### XMiR 固定基线与补丁

- 上游 commit：`16a46e350e3de2cb3415ab2cb652df53783998dc`
- `patches/xmir-d01-tested.patch`
  - `connect5.py`：增加 `--start-existing-ssh-only`；
  - `gateway.py`：隐藏密码输入、D01 ARMv7 回退、CRLF 归一化；
  - `passw.py`：隐藏新密码输入并安全传给 `passwd`；
  - `python/python38._pth`：让嵌入式 Python 能导入 XMiR 根目录模块；
  - `run.sh`：用 Python import 检测替代 GNU `find -wholename`，兼容 macOS BSD 工具链。

### SSH 适配

- `enable_ssh_d01.py`：跨平台依次编排首次 SSH、强制改密和 D01 持久化；
- `repair_d01_dropbear_boot.py`
- `data/payload_ssh/dropbear_d01.init.d.sh`
- `data/payload_ssh/dropbear_d01.firewall_hook.sh`

通用 Dropbear 二进制和安装 payload 由固定版本 XMiR-Patcher 提供，不在本仓库重复镜像。

### ShellCrash/Mihomo 分步安装

- `install_shellcrash_framework.py`
- `install_mihomo_armv7.py`
- `install_zashboard.py`
- `d01_failsafe.py`：三段受控启用流程共享的事务锁、进程身份与独立回滚编排；
- `import_d01_full_yaml.py`
- `prepare_d01_runtime_redir_host.py`
- `test_start_shellcrash.py`
- `test_enable_shellcrash_firewall.py`
- `install_shellcrash_d01_boot.py`
- `verify_d01_install.py`
- `export_d01_private_snapshot.py`

### ShellCrash payload

- `data/payload_shellcrash/d01_defaults.sh`
- `data/payload_shellcrash/d01_test_failsafe.sh`
- `data/payload_shellcrash/d01_firewall_failsafe.sh`
- `data/payload_shellcrash/d01_boot_failsafe.sh`
- `data/payload_shellcrash/d01_boot_transaction.sh`
- `data/payload_shellcrash/shellcrash_d01.init.d.sh`
- `data/payload_shellcrash/d01_firewall_hook.sh`
- `data/payload_shellcrash/d01_stability_monitor.sh`
- `data/payload_shellcrash/d01_diagnose_start.sh`

## B. 可公开的诊断工具

- `probe_d01_tproxy_capability.py`：临时链测试，结束后删除；
- `diagnose_shellcrash_start.py`：启动日志与运行态；
- `diagnose_d01_x_facebook.py`：区分客户端 DNS、Mihomo DNS、DoH 与 TCP；
- `diagnose_trojan_tun.py`：协议延迟与内核能力；
- `install_d01_stability_monitor.py`；
- `check_d01_stability_monitor.py`：只读确认探针文件、进程、最近采样和触发快照；
- `capture_broken_shellcrash_d01.py`：源码可公开，但输出绝对私有。

## C. 私人恢复包

以下内容不属于公开仓库：

- 最终成功状态的 `config.yaml`、`user.yaml`、`ShellCrash.cfg`、`cache.db`；
- 最终 `CrashCore.upx`、`geoip.metadb`、`cn.mrs` 的精确副本；
- 最终 ShellCrash/Dropbear init 与 hook；
- 原始完整 FClash YAML；
- 故障归档 `d01-shellcrash-broken-*.tar.gz`；
- 展开的 `inspect-*`；
- `d01_data_files.tar.gz`；
- `mtd0_*.bin` 到 `mtd17_*.bin`；
- `backups/SHA256SUMS.txt`；
- 0 字节的 `mtd18_data.bin` 仅可作为“备份缺失”记录，不能用于恢复；
- `outdir/` 下的 dmesg、分区和设备日志。

现有故障归档是重装前现场，DNS 修复后的最终状态必须用 `export_d01_private_snapshot.py` 重新导出。

## D. 私人专用、不能原样公开的成功脚本

- `reinstall_shellcrash_d01_redir_udp_direct.py`
  - 固定故障备份路径、SHA、旧 Dashboard secret；
  - 单独运行曾因检查条件误判停止。
- `resume_shellcrash_d01_redir_udp_direct.py`
  - 固定私人 `cache.db` 路径、长度和 SHA；
  - 依赖个人策略选择历史。
- `repair_d01_foreign_dns.py`
  - 固定个人策略组名、15 条替换和特定域名；
  - 公共版只保留 DNS 原理和示例。
- `import_fclash_config_d01.py`
  - 含私人输入 SHA 和专用重试开关；
  - 主流程由公开版 `import_d01_full_yaml.py` 取代。

## E. 历史中间方案/失败迭代

### SSH

- `connect6.py`：D01 1.0.72 漏洞链失败；
- `recover_ssh_from_telnet.py`；
- `start_ssh_from_telnet.py`；
- `install_d01_dropbear_init.py`；
- `finalize_ssh_boot.py`；
- 旧 `dropbear.init.d.sh`。

它们已被 `connect5.py --start-existing-ssh-only` 和 `repair_d01_dropbear_boot.py` 取代。

### 早期配置/启动

- `import_shellcrash_config.py`：本机 HTTPS 下载遇到 SSL 失败；
- `import_shellcrash_file.py`：Base64 URI 能生成节点，但不保留完整配置语义；
- 旧 `prepare_shellcrash_runtime.py`：把 DNS 改为 Fake-IP，不属于最终模式；
- `diagnose_d01_reinstall_runtime.py`；
- `diagnose_d01_core_launch.py`；
- `diagnose_last_fclash_failure.py`；
- `diagnose_trojan_handshake.py`：曾含个人本地路径，禁止原样发布；
- `d01_config_import_failsafe.sh`、`d01_dns_policy_failsafe.sh`：保留在私人历史，公共主流程不依赖。

### 未完成升级

- `upgrade_mihomo_v1_19_29.py`；
- `d01_mihomo_upgrade_failsafe.sh`；
- 所有 v1.19.29 下载、UPX 和临时文件。

它们未完成 D01 上的切换与重启验收。

## F. 第三方资产

公开仓库只保留 `vendor/SHA256SUMS.tested` 和来源。精确二进制进入私人恢复包：

| 文件 | 字节 | 用途 |
|---|---:|---|
| `ShellCrash.tar.gz` | 123627 | 框架 1.9.4release |
| `mihomo-shellcrash-armv7.upx` | 10185476 | 当前 v1.19.28 核心 |
| `zashboard.tar.gz` | 848404 | 可选离线面板 |

`firmware/` 中的 BE3600/BE7200 研究文件约数百 MiB，与 D01 教程无关，必须排除。
