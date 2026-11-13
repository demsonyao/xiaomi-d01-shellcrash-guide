# 安全与公开发布检查

## 绝不能公开

- 所有 `backups/`；
- MTD、UBI、rootfs 和 `/data` 镜像；
- `config.yaml`、`user.yaml`、`ShellCrash.cfg`、`cache.db`；
- 原始订阅文件；
- Mihomo Controller secret；
- Dropbear/HTTPS 私钥和 `/etc/shadow`；
- Wi-Fi、PPPoE、VPN 和小米账号配置；
- MAC、SN、客户端清单和完整 dmesg/logread；
- `capture_broken_shellcrash_d01.py` 生成的任何归档。

私人 GitHub 仓库也不适合保存这些内容。Git 历史、Release 附件和账号失陷会扩大泄露面。建议使用 7-Zip AES-256、age 或加密磁盘，口令与归档分开保存。

## 网络暴露

- root 密码不能保持为 `root`；
- 不要在上级设备做 22、7890、9999 端口转发；
- 只要 Controller 监听 LAN `:9999`，无论是否安装 Dashboard，都必须设置唯一 secret；
- 若安装 Dashboard，应使用该 Controller secret 登录；
- 面板和代理端口只对可信 LAN 开放；
- D01 的 WAN 接口名是 `eth0`。本项目的 boot init/firewall hook 会在 IPv4/IPv6 INPUT 顶部阻断来自 `eth0` 的 22、80、443、7890、9999（以及 UDP 7890/9999），并把 `replace_default_host_ipv4` 固定为 `ON`，避免把上级私网自动并入可信管理网段；
- 家庭上级设备也应关闭远程管理和 UPnP 自动映射，或至少定期检查映射；
- 本方案 UDP 直连，外部网络能看到这些 UDP 目的地址和时序；这与没有代理时的普通游戏直连相同。
- `:9999` Controller/Zashboard 是可信 LAN 内的明文 HTTP；secret 只提供访问认证，不加密传输。使用独立高熵值，并且不要从 WAN 转发 9999。

## 发布前文件检查

本节是仓库维护者流程，目前使用 PowerShell；路由安装、备份、诊断与恢复的跨平台入口见 [PLATFORMS.md](PLATFORMS.md)。

先运行仓库自带审计：

```powershell
Set-Location -LiteralPath '.\xiaomi-d01-shellcrash-guide'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\audit-public.ps1'
```

如有本机专属痕迹（用户名、已知配置哈希、订阅文件名），把它们逐行写进仓库外的私人 denylist，再运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\audit-public.ps1' `
  -LocalDenylist 'C:\私人目录\public-audit-denylist.txt'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tools\build-release.ps1' `
  -LocalDenylist 'C:\私人目录\public-audit-denylist.txt'
```

构建器会在压缩后再次打开 ZIP，审计内部文件名与内容，并逐文件比较 ZIP 和当前源码的 SHA256，避免发布陈旧或夹带额外文件的压缩包。

再检查 Git 实际会提交什么：

```powershell
git status --short --ignored
git diff --cached --name-only
git ls-files | rg '(^|/)(backups|private|captures|outdir|firmware|subscriptions)/'
```

只显示命中文件名、不回显秘密内容：

```powershell
rg -l -uuu --hidden --glob '!.git/**' --pcre2 `
'(?i)(trojan|vless|vmess|ssr?|hysteria2|hy2)://|-----BEGIN .*PRIVATE KEY-----|\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b'
```

压缩包不会总被普通源码扫描器展开检查。仓库构建器已经审计自己的发布 ZIP；任何其他 `.zip`、`.tar.gz` 仍必须在仓库外解压后再扫描文件名和内容。

## 凭据已误提交时

从最新提交删除不够。必须：

1. 轮换订阅、节点密码、root 密码和 Controller secret；
2. 移除 Git 历史中的文件；
3. 删除旧 Release/缓存/镜像；
4. 重新扫描完整历史；
5. 通知受影响的凭据提供方。

## 许可证

不要把“网上可下载”等同于“可无条件再分发”。上游来源和许可证见 [THIRD_PARTY.md](../THIRD_PARTY.md)。XMiR-Patcher 当前根仓库未见明确许可证，本项目只发布适配补丁和使用说明。
