# 小米路由器 Mesh D01：SSH + ShellCrash + Mihomo

这是一套针对小米路由器 Mesh D01 的分步适配记录。它不是通用小米路由器教程，也不是一键脚本。

> 首次公开版 `v1.0.0`。SSH、legacy init、Mihomo、TCP Redir、redir-host、UDP 直连、DNS 修复和重启恢复已在 Windows x64 和目标 D01 上跑通。后续使用出现过间歇断网，故障原因未确认。公开脚本尚待恢复出厂后的完整复演，Linux/macOS 入口尚待实机验收。

实测基线：

- 型号：D01
- ROM：MiWiFi 稳定版 `1.0.72`
- 内核/架构：Linux `3.14.77` / ARMv7
- ShellCrash：`1.9.4release`
- Mihomo：`v1.19.28` ARMv7 UPX
- 透明代理：IPv4 TCP Redir
- DNS：redir-host，Mihomo 监听 `:1053`
- UDP：普通 UDP 与游戏 UDP 直连，不进入 Mihomo
- IPv6 透明代理：关闭
- Controller：监听 `:9999`，必须设置 secret；未授权健康检查应返回 HTTP 401
- 可选面板：Zashboard，安装后默认 `http://192.168.31.1:9999/ui/`

## 三步安装主线

真正安装到路由器上的核心只有三步；其他章节是备份、配置和验收：

### 1. 开启并持久化 SSH

按 [SSH 章节](docs/01-SSH.md) 准备固定 XMiR 版本和 D01 补丁，然后运行统一入口：

Windows：

```powershell
.\run.bat enable_ssh_d01.py
```

Linux/macOS：

```bash
./run.sh enable_ssh_d01.py
```

它仍把三个安全边界清楚分开执行：XMiR SmartController 入口 → 隐藏输入并更换 root 密码 → 安装 D01 Dropbear legacy-init；任一步失败都会停止，不会把密码放进命令行。

### 2. 安装 ShellCrash 框架

先完成 [MTD 备份](docs/02-BACKUP.md)，再运行：

```powershell
.\run.bat install_shellcrash_framework.py
```

```bash
./run.sh install_shellcrash_framework.py
```

### 3. 安装 ARMv7 Mihomo 内核

```powershell
.\run.bat install_mihomo_armv7.py
```

```bash
./run.sh install_mihomo_armv7.py
```

Zashboard 只是可选管理面板，不属于必需核心：

```powershell
.\run.bat install_zashboard.py
```

```bash
./run.sh install_zashboard.py
```

不装面板也不等于可以省略 Controller 认证：后续运行时准备会在 secret 缺失时隐藏询问并持久保存密码，未授权 API 必须返回 HTTP 401。

安装完成后不是再装第四个组件，而是按 [配置建议](docs/05-CONFIG.md) 导入自己的完整 YAML，并用 [受控启用与重启验收](docs/04-INSTALL.md#6-导入完整-yaml但保持停机安全锁) 完成：`Redir + redir-host(:1053) + IPv6 关闭 + UDP 直连`。D01 专用自启和防火墙 hook 是 ShellCrash 安装的收尾，不是另一个软件包。

## 最终效果和边界

这套方案能让经过主 D01 的 IPv4 TCP 流量按 Mihomo 规则分流，同时保留真实 DNS 地址，让未被透明代理接管的游戏 UDP 可以正常直连。

D01 原厂固件实测没有 `/dev/net/tun`，也无法真正插入 TPROXY 内核规则。因此：

- 不支持 TUN；
- 不支持 UDP TProxy；
- 面板里出现 TUN/TProxy 选项，不代表内核具备能力；
- 如果必须让 UDP 也透明代理，应换用具备 TUN/TPROXY 支持的路由系统，而不是继续修改本方案。

两台 D01 有线 Mesh 时，只需在作为默认网关的主节点安装。子节点仍负责无线接入和 Mesh 回程，客户端流量最终由主路由分流。

## 这套成果来自哪里

本项目是“上游组件 + D01 适配层”：

- SmartController 漏洞原理来自 CVE-2023-26319 的公开研究；
- Web 入口、设备通信和基础 Dropbear 部署来自 XMiR-Patcher；
- ShellCrash、Mihomo、Zashboard 分别来自各自上游；
- 本项目新增并实测了 D01 的 Dropbear legacy-init 持久化、ShellCrash legacy 启动、iptables Redir、防火墙钩子、失败回滚、能力探测和诊断流程。

原始 XMiR 流程在这台 D01 上曾只稳定得到 Telnet 23 端口。D01 适配补丁增加了 ARMv7 架构回退、CRLF 归一化、已安装 Dropbear 的无改密恢复，以及适用于传统 PID 1 `init` 的启动服务。

完整引用见 [上游来源与许可证](THIRD_PARTY.md) 和 [参考资料](docs/REFERENCES.md)。

## 阅读顺序

1. [Windows、macOS 与 Linux 运行方式](docs/PLATFORMS.md)
2. [范围、安全与拓扑](docs/00-SCOPE.md)
3. [开启并持久化 SSH](docs/01-SSH.md)
4. [先做备份](docs/02-BACKUP.md)
5. [确认 TUN/TPROXY 能力](docs/03-CAPABILITY.md)
6. [分步安装 ShellCrash、Mihomo 与可选 Zashboard](docs/04-INSTALL.md)
7. [导入自己的订阅、规则和 redir-host DNS](docs/05-CONFIG.md)
8. [自启、重启和最终验收](docs/06-VERIFY.md)
9. [故障排查与安全停止](docs/07-TROUBLESHOOTING.md)
10. [完整文件清单与分类](docs/FILES.md)
11. [公开发布前的脱敏检查](docs/SECURITY.md)

## 仓库结构

```text
xiaomi-d01-shellcrash-guide/
├─ README.md
├─ THIRD_PARTY.md
├─ docs/                   教程、排障、文件清单和安全说明
├─ d01-overlay/            覆盖到 XMiR-Patcher 根目录的 D01 脚本
├─ patches/                针对固定 XMiR commit 的补丁
├─ examples/               不含真实节点的配置片段
├─ vendor/                 只记录上游资产及校验值，不提交二进制
└─ tools/                  打包、校验和公开内容审计
```

## 当前发布基线

本文安装器固定使用 Mihomo `v1.19.28`。框架和内核的固定下载链接及 SHA256 见 [第三方资产](THIRD_PARTY.md#本次实际使用的本地资产)。
