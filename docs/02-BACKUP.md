# 备份：先保存原始闪存，再保存最终应用状态

## 原始 MTD 备份

SSH 正常后，在 XMiR-Patcher 根目录运行：

```powershell
.\run.bat create_backup.py
```

```bash
./run.sh create_backup.py
```

备份目录里应包含 bootloader、kernel、rootfs、overlay、cfgbak、ubirootfs 等分区。逐个检查文件非零并生成 SHA256：

```powershell
Get-ChildItem -LiteralPath '.\backups' -File -Filter 'mtd*.bin' |
  ForEach-Object {
    [pscustomobject]@{
      Name = $_.Name
      Bytes = $_.Length
      SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
    }
  } | Format-Table -AutoSize
```

Linux 先确认文件非零，再生成哈希：

```bash
for file in backups/mtd*.bin; do [ -s "$file" ] || printf 'EMPTY %s\n' "$file"; done
sha256sum backups/mtd*.bin
```

macOS：

```bash
for file in backups/mtd*.bin; do [ -s "$file" ] || printf 'EMPTY %s\n' "$file"; done
shasum -a 256 backups/mtd*.bin
```

第一条命令必须没有输出；否则存在 0 字节备份。

本次实测里 `mtd18_data.bin` 下载失败并留下 0 字节文件。出现这种情况时，不能把目录称为完整镜像，也不能用 0 字节文件恢复。

`create_backup.py` 最后打印 `Completed!` 也不等于每个分区都已完整下载；应以逐文件非零尺寸和 SHA256 清单为准。

不要把 MTD 镜像上传到 GitHub。它们可能包含：

- ART/校准数据；
- MAC、SN 和设备身份；
- Wi-Fi、PPPoE、VPN 和小米账号配置；
- root shadow 哈希；
- SSH/HTTPS 私钥；
- 客户端记录和历史日志。

## 最终应用快照

原始 MTD 备份不能代替最终 ShellCrash 快照。所有配置完成并通过重启后，运行：

先在公开仓库外准备一个明确标记的私人目录；这个标记也能防止导出器误把秘密写进普通 Git 工作区：

```powershell
$privateRoot = '..\d01-private-recovery'
New-Item -ItemType Directory -Path "$privateRoot\live-final" -Force | Out-Null
Set-Content -LiteralPath "$privateRoot\PRIVATE-ROOT.marker" `
  -Value 'PRIVATE D01 RECOVERY — DO NOT COMMIT' -Encoding UTF8

.\run.bat export_d01_private_snapshot.py --output "$privateRoot\live-final"
```

Linux/macOS：

```bash
private_root='../d01-private-recovery'
mkdir -p "$private_root/live-final"
printf '%s\n' 'PRIVATE D01 RECOVERY — DO NOT COMMIT' > "$private_root/PRIVATE-ROOT.marker"
./run.sh export_d01_private_snapshot.py --output "$private_root/live-final"
```

导出工具只读路由器，保存：

```text
/data/ShellCrash/yamls/config.yaml
/data/ShellCrash/yamls/user.yaml（存在时）
/data/ShellCrash/configs/ShellCrash.cfg
/data/ShellCrash/cache.db
/data/ShellCrash/CrashCore.upx
/data/ShellCrash/geoip.metadb
/data/ShellCrash/ruleset/cn.mrs
/data/shellcrash_firewall_hook.sh
/etc/init.d/shellcrash_d01
/data/dropbear_d01_firewall_hook.sh
/etc/init.d/dropbear
```

输出目录包含真实节点、订阅信息和 Mihomo Controller secret，必须位于公开仓库外，并用加密磁盘或加密归档保存。

现有 `d01-shellcrash-broken-*.tar.gz` 是故障现场，不是最终恢复金本。不要拿它替代安装成功后的新快照。该快照是“应用状态金本”；完整恢复仍需同时保留固定版本的三个离线资产、XMiR 基线/补丁和原始 MTD 备份。
