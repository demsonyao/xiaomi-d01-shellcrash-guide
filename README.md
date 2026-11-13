# Xiaomi Mesh Router D01: SSH + ShellCrash + Mihomo

English · [简体中文](README.zh-CN.md)

This guide documents a manual setup for the Xiaomi Mesh Router D01. It applies to the hardware and firmware listed below.

> First public release: `v1.0.0`. SSH, legacy init, Mihomo, TCP Redir, redir-host, direct UDP, the DNS fix, and recovery after reboot were tested on the target D01 using a Windows x64 computer. Intermittent outages occurred during later use, and their cause remains unknown. The public scripts have yet to be tested end to end from a factory reset. The Linux and macOS entry points still need testing on physical hardware.

## Tested setup

- Model: D01
- Firmware: MiWiFi stable `1.0.72`
- Kernel and architecture: Linux `3.14.77` on ARMv7
- ShellCrash: `1.9.4release`
- Mihomo: `v1.19.28`, ARMv7 UPX build
- Transparent proxying: IPv4 TCP Redir
- DNS: redir-host, with Mihomo listening on `:1053`
- UDP: regular UDP and game traffic go directly out, bypassing Mihomo
- IPv6 transparent proxying: disabled
- Controller API: listens on `:9999` and requires a secret. An unauthenticated health check should return HTTP 401.
- Optional dashboard: Zashboard, available at `http://192.168.31.1:9999/ui/` by default after installation

## Installation in three steps

### 1. Enable SSH and make it persistent

Use the [SSH instructions](docs/01-SSH.md) to prepare the pinned XMiR-Patcher revision and apply the D01 patch. Then run the installer for your platform.

Windows

```powershell
.\run.bat enable_ssh_d01.py
```

Linux and macOS

```bash
./run.sh enable_ssh_d01.py
```

The installer runs three stages. It uses XMiR's SmartController entry point, prompts for a new root password without echoing it, and installs the D01 Dropbear service for legacy init. It stops if any stage fails and keeps passwords off the command line.

### 2. Install the ShellCrash framework

Complete the [MTD backup](docs/02-BACKUP.md) before running the installation.

```powershell
.\run.bat install_shellcrash_framework.py
```

```bash
./run.sh install_shellcrash_framework.py
```

### 3. Install the ARMv7 Mihomo core

```powershell
.\run.bat install_mihomo_armv7.py
```

```bash
./run.sh install_mihomo_armv7.py
```

You can also install the optional Zashboard dashboard.

```powershell
.\run.bat install_zashboard.py
```

```bash
./run.sh install_zashboard.py
```

The Controller API requires authentication even if you skip Zashboard. If the secret is missing, the runtime setup prompts for it without echoing the input and saves it. Unauthenticated API requests must return HTTP 401.

Follow the [configuration guide](docs/05-CONFIG.md) to import your full YAML, then follow the [controlled activation and reboot checks](docs/04-INSTALL.md#6-导入完整-yaml但保持停机安全锁). The setup uses TCP Redir, redir-host on port 1053, direct UDP, and disabled IPv6 transparent proxying. The D01-specific startup service and firewall hook complete the ShellCrash setup.

## Traffic handling and limitations

Mihomo applies its routing rules to IPv4 TCP traffic that passes through the main D01. DNS returns real IP addresses, and game UDP goes out directly.

The tested stock firmware lacks `/dev/net/tun` and rejects TPROXY rules. TUN and transparent UDP proxying are therefore unavailable on this setup, even if the dashboard displays those options. Transparent UDP proxying requires a routing platform with TUN or TPROXY support.

In a two-node wired D01 Mesh, install this setup on the main node that serves as the default gateway. The secondary node continues to provide Wi-Fi access and Mesh backhaul. The main node handles client traffic according to the routing rules.

## Upstream projects and D01 adaptations

- The SmartController vulnerability is documented in the public research behind CVE-2023-26319.
- XMiR-Patcher provides the web entry point, device communication, and basic Dropbear deployment.
- ShellCrash, Mihomo, and Zashboard come from their respective upstream projects.
- This project adapts and tests Dropbear persistence under legacy init, ShellCrash startup, iptables Redir, firewall hooks, rollback, capability checks, and diagnostics on the D01.

On the tested D01, the original XMiR procedure reliably exposed only Telnet on port 23. The D01 patch adds an ARMv7 detection fallback, CRLF normalization, recovery of an existing Dropbear installation without changing its password, and a startup service for the traditional PID 1 `init`.

See the [upstream projects and licenses](THIRD_PARTY.md) and [references](docs/REFERENCES.md) for attribution and sources.

## Detailed documentation

The linked chapters are in Simplified Chinese.

1. [Running on Windows, macOS, and Linux](docs/PLATFORMS.md)
2. [Scope, safety, and network topology](docs/00-SCOPE.md)
3. [Enabling and persisting SSH](docs/01-SSH.md)
4. [Making a backup](docs/02-BACKUP.md)
5. [Checking TUN and TPROXY support](docs/03-CAPABILITY.md)
6. [Installing ShellCrash, Mihomo, and optional Zashboard](docs/04-INSTALL.md)
7. [Importing your subscription and rules, and configuring redir-host DNS](docs/05-CONFIG.md)
8. [Autostart, reboot, and final verification](docs/06-VERIFY.md)
9. [Troubleshooting and stopping the service safely](docs/07-TROUBLESHOOTING.md)
10. [File inventory](docs/FILES.md)
11. [Checking for private data before publishing](docs/SECURITY.md)

## Repository layout

```text
xiaomi-d01-shellcrash-guide/
├── README.md              English README
├── README.zh-CN.md        Simplified Chinese README
├── THIRD_PARTY.md         Upstream sources and licenses
├── docs/                  Instructions, troubleshooting, and security notes
├── d01-overlay/           D01 scripts copied into the XMiR-Patcher directory
├── patches/               Patch for the pinned XMiR-Patcher revision
├── examples/              Configuration snippets with no real proxy nodes
├── vendor/                Upstream asset references and checksums
└── tools/                 Packaging and privacy checks
```

## Pinned release assets

The installer pins Mihomo to `v1.19.28`. See the [third-party asset list](THIRD_PARTY.md#本次实际使用的本地资产) for the framework and core download links and SHA256 checksums.
