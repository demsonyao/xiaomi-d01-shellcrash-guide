# 开启并持久化 SSH

## 1. 准备固定版本的 XMiR-Patcher

先阅读[平台运行方式](PLATFORMS.md)，安装本机所需的 Git、Python/OpenSSL 依赖。

Windows PowerShell：

```powershell
Set-Location -LiteralPath 'C:\Users\<YOU>\Documents\Tweaks'
git clone https://github.com/openwrt-xiaomi/xmir-patcher.git
Set-Location -LiteralPath '.\xmir-patcher'
git checkout 16a46e350e3de2cb3415ab2cb652df53783998dc
git apply '..\xiaomi-d01-shellcrash-guide\patches\xmir-d01-tested.patch'
Copy-Item -Path '..\xiaomi-d01-shellcrash-guide\d01-overlay\*' -Destination '.' -Recurse -Force
```

Linux/macOS：

```bash
cd "$HOME/Documents/Tweaks"
git clone https://github.com/openwrt-xiaomi/xmir-patcher.git
cd xmir-patcher
git checkout 16a46e350e3de2cb3415ab2cb652df53783998dc
git apply ../xiaomi-d01-shellcrash-guide/patches/xmir-d01-tested.patch
cp -R ../xiaomi-d01-shellcrash-guide/d01-overlay/. .
```

补丁只针对上面的固定 commit。若 `git apply` 报冲突，不要强制套用；先比较上游变化。

## 2. 确认型号

```powershell
.\run.bat read_info.py
```

```bash
./run.sh read_info.py
```

必须看到：

```text
device_name = D01
rom_version = 1.0.72 release
```

否则停止。

## 3. 推荐：运行 D01 SSH 统一入口

```powershell
.\run.bat enable_ssh_d01.py
```

```bash
./run.sh enable_ssh_d01.py
```

默认 `first-install` 会按顺序运行：

1. 固定版 XMiR `connect5.py`，通过 SmartController 部署并启动 Dropbear；
2. `passw.py`，强制把临时 root 密码换成你自己的唯一强密码；
3. `repair_d01_dropbear_boot.py`，安装 D01 传统 `init` 的 `S19/K50` 链接和安全防火墙 hook。

所有 Web/root 密码都由 Python 脚本隐藏输入；统一入口不接收、不保存也不打印密码。任一步返回非零即停止。入口还会为路由本地地址设置当前进程的 `NO_PROXY`，避免桌面代理/VPN 接管 Web API。

> 如果第 1 步已经成功而第 2 步意外中止，路由可能暂时保留弱 root 密码 `root`。不要离开当前可信 LAN；立即用对应平台入口运行 `passw.py`，确认新密码可登录后再继续。

最终成功标志：

```text
D01_DROPBEAR_BOOT_REPAIRED_NO_RESTART
ACTIVE_SSH_PROCESS_UNCHANGED
D01_SSH_INSTALL_COMPLETE
```

引用与贡献边界：SmartController 命令注入研究来自 THALIUM 的 Julien R.、Marin Duroyon 与 CVE-2023-26319；小米 Web/设备通信及基础 Dropbear 部署来自 XMiR-Patcher；本项目提供 D01 1.0.72 的 ARMv7/CRLF 补丁、无改密 SSH 恢复入口和 legacy-init 持久化。固定链接见 [参考资料](REFERENCES.md#漏洞与-ssh-入口)，许可证/再分发说明见 [THIRD_PARTY](../THIRD_PARTY.md)。

## 4. 手工拆分：运行 SmartController 入口

```powershell
.\run.bat connect5.py
```

```bash
./run.sh connect5.py
```

脚本会交互式询问路由 Web 管理密码。不要把密码追加到命令行。

这一步基于 XMiR-Patcher 的 `connect5.py` 和 CVE-2023-26319 公开研究。D01 补丁补充了：

- `/etc/openwrt_release` 不存在时用 `uname -m` 识别 ARMv7；
- 上传 Shell 脚本后去除 Windows CRLF；
- 密码输入不回显；
- 已安装 Dropbear 的恢复入口。

历史上，未打补丁的流程在 D01 上可能显示 Telnet 已开启，随后因读不到 `/etc/openwrt_release` 而无法完成 SSH。

## 5. 只有 Telnet 或重启后 SSH 消失时

若 Dropbear 已经落盘，但 22 端口没监听：

```powershell
.\run.bat enable_ssh_d01.py --mode recover-existing
```

```bash
./run.sh enable_ssh_d01.py --mode recover-existing
```

成功标志：

```text
RECOVERY_ONLY_SUCCESS: SSH is responding on port 22
```

这个模式不会改 root 密码，也不会重新开启 Telnet；SSH 恢复后会继续确认 D01 开机持久化。若 SSH 已经正常、只需修复开机服务，可用 `--mode repair-only`。

## 6. 手工拆分：立刻修改 root 密码

首次 XMiR 流程可能把 root 临时设为弱密码 `root`。SSH 一旦可用，立即运行：

```powershell
.\run.bat passw.py
```

```bash
./run.sh passw.py
```

输入一个唯一强密码。不要在公开日志中展示它。

## 7. 手工拆分：安装 D01 legacy-init 持久化

```powershell
.\run.bat repair_d01_dropbear_boot.py
```

```bash
./run.sh repair_d01_dropbear_boot.py
```

必须看到：

```text
D01_DROPBEAR_BOOT_REPAIRED_NO_RESTART
ACTIVE_SSH_PROCESS_UNCHANGED
```

为什么需要它：D01 的 PID 1 是传统 `init`，而通用 Dropbear 安装器写入的是偏向 procd 的启动方式。适配脚本安装：

```text
/etc/rc.d/S19dropbear -> ../init.d/dropbear
/etc/rc.d/K50dropbear -> ../init.d/dropbear
/data/dropbear_d01_firewall_hook.sh
```

它不会故意重启当前 SSH 进程，避免在修复过程中切断连接。

先继续做完整备份；最终重启测试放在 [验收章节](06-VERIFY.md)。
