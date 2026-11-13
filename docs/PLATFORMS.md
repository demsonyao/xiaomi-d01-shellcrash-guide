# Windows、macOS 与 Linux 运行方式

本项目沿用 XMiR-Patcher 的启动逻辑：D01 工具全部是同一套 Python 脚本，只由平台入口区分。

| 平台 | 入口 | 本项目验证状态 |
|---|---|---|
| Windows 10/11 x64 | `run.bat SCRIPT.py [参数]` | D01 1.0.72 完整成功链实测 |
| Linux | `./run.sh SCRIPT.py [参数]` | 代码、补丁和脚本静态检查通过，尚未做本项目的 D01 端到端复演 |
| macOS Intel / Apple Silicon | `./run.sh SCRIPT.py [参数]` | 已修正上游 GNU `find` 依赖，尚未做本项目的 D01 端到端复演 |

公开包的“跨平台”是指安装、备份、诊断、恢复和验收这些终端用户流程。`tools/*.ps1` 是仓库维护者用于脱敏审计和构建 ZIP 的工具，目前仍需 PowerShell，不影响路由安装流程。

## Windows

需要 Git；XMiR-Patcher 仓库自带 Windows x64 Python 运行时，不要另行 `pip install`，也不需要管理员 PowerShell。

在 XMiR 根目录运行：

```powershell
.\run.bat enable_ssh_d01.py
.\run.bat install_shellcrash_framework.py
.\run.bat install_mihomo_armv7.py
```

不要删除或拆散 XMiR 的 `python/` 目录。Windows 32 位和 Windows ARM64 原生运行没有在本项目验证。

## Linux

先安装 Git、Bash、Python 3.8+、Python venv、OpenSSL 和 CA 证书。以 Debian/Ubuntu 为例：

```bash
sudo apt update
sudo apt install -y git bash python3 python3-venv python3-pip openssl ca-certificates
```

`sudo` 只用于安装系统包；不要用 `sudo` 运行 XMiR。进入 XMiR 根目录后：

```bash
./run.sh enable_ssh_d01.py
./run.sh install_shellcrash_framework.py
./run.sh install_mihomo_armv7.py
```

`run.sh` 会创建/复用 `venv/`，并按 `requirements.txt` 安装依赖。若文件的执行位在 ZIP 解压时丢失，可写成 `bash ./run.sh SCRIPT.py`。

少数平台没有 `ssh2-python` wheel、需要本地编译；这时再按发行版安装编译器、CMake 和 Python 开发头文件，不要全局使用 `sudo pip`。

## macOS

推荐 Homebrew Python 或 python.org Python，不依赖旧的系统 Python：

```bash
brew install git python openssl
```

然后在 XMiR 根目录使用与 Linux 相同的入口：

```bash
./run.sh enable_ssh_d01.py
./run.sh install_shellcrash_framework.py
./run.sh install_mihomo_armv7.py
```

固定补丁把上游 `run.sh` 中仅 GNU `find` 支持的 `-wholename` 检测，改成了可移植的 Python import 检测；因此不要跳过 `patches/xmir-d01-tested.patch`。如果 `ssh2-python` 必须源码编译，可能还需要 Xcode Command Line Tools 和 CMake。

## 本机网络准备

- 电脑连接目标 D01 的普通 LAN，能打开 `http://192.168.31.1`；
- 不使用访客 Wi-Fi或客户端隔离；
- VPN 或另一张网卡不能占用 `192.168.31.0/24`；
- 安装期间保持电脑和路由器供电，关闭自动睡眠；
- 不需要关闭系统防火墙或杀毒软件。

`enable_ssh_d01.py` 会自动把 `192.168.31.1`、`localhost`、`127.0.0.1` 加入当前进程及子进程的 `NO_PROXY`，避免桌面 VPN/HTTP 代理劫持路由 Web API。手工运行其他 XMiR Web 工具时可先设置：

Windows PowerShell：

```powershell
$env:NO_PROXY = '192.168.31.1,localhost,127.0.0.1'
$env:no_proxy = $env:NO_PROXY
```

Linux/macOS：

```bash
export NO_PROXY='192.168.31.1,localhost,127.0.0.1'
export no_proxy="$NO_PROXY"
```

## 固定边界

- 所有命令都必须从 XMiR-Patcher 根目录运行；
- D01 主线只调用 `enable_ssh_d01.py` / `connect5.py`，不要改用会尝试 Windows `netsh.exe` 的 `connect7.py`；
- Python 3.8 是最低版本，Linux/macOS 推荐 3.10 或 3.11；
- Unix 依赖并非字节级锁定，复演时应记录 `python3 --version` 和 `python3 -m pip freeze`；
- 当前 Linux/macOS 结论是“支持的代码路径”，不是已经完成的实机成功声明。

XMiR-Patcher 的原始平台说明、`run.sh` 和依赖文件见[参考资料](REFERENCES.md#xmir-patcher-平台入口)。
