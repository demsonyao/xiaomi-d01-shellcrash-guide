# 分步安装 ShellCrash、Mihomo 与可选 Zashboard

所有命令都在 XMiR-Patcher 根目录运行。Windows 使用 `run.bat SCRIPT.py [参数]`，Linux/macOS 使用 `./run.sh SCRIPT.py [参数]`。每一步都单独验证；出现 `*_FAILED` 时停止，不要继续下一步。

## 1. 准备本地资产

按 [实测资产表](../THIRD_PARTY.md#本次实际使用的本地资产) 下载固定的 ShellCrash 框架和 ARMv7 内核。只有手头已有同一份 Zashboard 离线归档时才执行可选面板步骤。

推荐目录：

```text
Tweaks/
├─ xmir-patcher/
├─ xiaomi-d01-shellcrash-guide/
└─ shellcrash-package/
   ├─ ShellCrash.tar.gz
   ├─ zashboard.tar.gz              仅安装可选面板时需要
   └─ cores/
      └─ mihomo-shellcrash-armv7.upx
```

校验：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath `
  '..\shellcrash-package\ShellCrash.tar.gz', `
  '..\shellcrash-package\cores\mihomo-shellcrash-armv7.upx', `
  '..\shellcrash-package\zashboard.tar.gz'
```

Linux：

```bash
sha256sum ../shellcrash-package/ShellCrash.tar.gz \
  ../shellcrash-package/cores/mihomo-shellcrash-armv7.upx \
  ../shellcrash-package/zashboard.tar.gz
```

macOS 将 `sha256sum` 换成 `shasum -a 256`。如果不安装 Zashboard，可从命令中删除它的路径。

必须与 [THIRD_PARTY.md](../THIRD_PARTY.md) 的本次实测值相符。若使用不同上游版本，应先审阅脚本和资源占用，再更新你自己的清单，不能跳过哈希验证。

## 2. 安装 ShellCrash 框架

```powershell
.\run.bat install_shellcrash_framework.py
```

```bash
./run.sh install_shellcrash_framework.py
```

成功标志：

```text
FRAMEWORK_OK
SHELLCRASH_FRAMEWORK_INSTALLED
CORE_NOT_RUNNING
```

此时不应接管流量。

**从这一步开始到第 10 步安装 D01 legacy-init 服务之前不要重启路由器。** 框架初始安装的通用启动钩子尚未替换成 D01 专用版本；中途重启不属于本教程的安全路径。

## 3. 安装 ARMv7 Mihomo 核心

```powershell
.\run.bat install_mihomo_armv7.py
```

```bash
./run.sh install_mihomo_armv7.py
```

成功标志：

```text
Mihomo Meta v1.19.28 linux arm
MIHOMO_ARMV7_INSTALLED_NOT_STARTED
```

UPX 是磁盘压缩，不代表运行内存按 9.7 MiB 计算；启动后核心仍会解压并加载规则、DNS 和连接状态。

## 4. 可选：安装 Zashboard

```powershell
.\run.bat install_zashboard.py
```

```bash
./run.sh install_zashboard.py
```

成功标志：

```text
ZASHBOARD_INSTALLED_NOT_STARTED=http://192.168.31.1:9999/ui/
```

安装器会隐藏询问并设置 Mihomo Controller 密码；它既保护 `:9999` API，也是 Zashboard 登录凭据。未授权 Controller 请求返回 HTTP 401 是本教程的必需健康状态，不是服务故障。

## 5. 准备自己的完整 Mihomo YAML

公开教程不提供订阅，也不内置规则。输入文件必须是完整 YAML，并至少包含：

```text
dns:
proxies: 或 proxy-providers:
proxy-groups:
rules:
```

请先按 [配置章节](05-CONFIG.md) 改成 redir-host，并关闭 TUN。不要把订阅 URL、UUID、password、private-key 或完整 YAML 提交到 GitHub。

## 6. 导入完整 YAML，但保持停机安全锁

```powershell
.\run.bat import_d01_full_yaml.py 'C:\路径\到\你的-config.yaml'
```

```bash
./run.sh import_d01_full_yaml.py '/path/to/your-config.yaml'
```

成功标志：

```text
INPUT_FULL_YAML_OK
CANDIDATE_VALID
D01_CONFIG_IMPORTED_NOT_STARTED
SHELLCRASH_DNS_OVERLAY_READY
AUTOSTART_DISABLED_UNTIL_TESTED
```

导入器会把完整 YAML 保存为 `yamls/config.yaml`，并把其中经过检查的完整 `dns:` 子树单独保存为权限 `0600` 的 `yamls/user.yaml`。这是 ShellCrash 1.9.4 的合并要求：节点、策略组和规则来自完整配置，而 DNS overlay 可防止运行时生成器把 redir-host 改回 fake-ip。两个文件会一起备份、替换；失败时一起恢复，原先不存在的文件也不会被残留候选污染。

本工具只接受一个普通块形式的顶层 `dns:`，拒绝重复/inline/anchor 形式和 Base64 URI 节点列表。实测中，简单 URI 转换会丢失完整 DNS、策略组和规则语义，导致节点测速与实际使用不一致。

## 7. 生成 redir-host 运行配置

```powershell
.\run.bat prepare_d01_runtime_redir_host.py
```

```bash
./run.sh prepare_d01_runtime_redir_host.py
```

必须看到：

```text
RUNTIME_CORE_LINK_READY
RUNTIME_REDIR_HOST_VALID
CONTROLLER_AUTH=SECRET_REQUIRED_HTTP_401
RUNTIME_PREPARED_NOT_STARTED
```

如果前面没有安装 Zashboard、ShellCrash 也没有现有 Controller secret，本步骤会隐藏询问并持久保存一个 12–64 字符的 Controller 密码。即使完全不使用图形面板，只要 Controller 监听 `:9999`，这个密码也不能省略。

`/tmp/ShellCrash` 是易失目录。脚本会重建：

```text
/tmp/ShellCrash/CrashCore -> /data/ShellCrash/CrashCore.upx
```

## 8. 只启动已准备的核心，不先接管 LAN 流量

```powershell
.\run.bat test_start_shellcrash.py
```

```bash
./run.sh test_start_shellcrash.py
```

成功标志：

```text
CONTROLLER_API_HTTP=401
```

并且：

```text
CONTROLLED_START_OK_AUTOSTART_STILL_DISABLED
```

若已完整安装 Zashboard，还会看到 `DASHBOARD_OPTIONAL_STATUS=READY` 和 `DASHBOARD_READY=...`；没有安装则报告 `NOT_INSTALLED`。只有 `ui/index.html`、`ui/manifest.webmanifest` 与至少一个 JavaScript 资产都存在时才会发起面板 HTTP 检查；仅有部分文件时报告 `PARTIAL`，不会把 ShellCrash 占位页或残缺目录误当成完整面板。新版官方 Release 不再保证包含 `CNAME`，因此它不能作为完整性标记。

此脚本直接通过 ShellCrash `start_legacy` 启动第 7 步已经生成并校验的 `/tmp/ShellCrash/config.yaml`，不会再调用一次完整的 `start.sh start` 重新生成配置。

先确认主策略指向实测可用的节点：可以用 Zashboard 或其他兼容 Mihomo Controller 客户端，也可以在 YAML 中预先选定。不要在主策略仍不可用时启用透明防火墙。

## 9. 启用 TCP Redir 防火墙

```powershell
.\run.bat test_enable_shellcrash_firewall.py
```

```bash
./run.sh test_enable_shellcrash_firewall.py
```

成功判断以规则和联网验证为准：

```text
SHELLCRASH_FIREWALL_REFS=>0
CLIENT_CONNECTIVITY_ATTEMPT_1_HTTP_STATUS=204
TRANSPARENT_PROXY_OK_AUTOSTART_STILL_DISABLED
```

ShellCrash 某些脚本即使返回 `rc=1`，仍可能已经正确创建规则；不能只看返回码。若规则数为 0 或客户端无法取得严格的 HTTP 204，控制端只负责唤醒已经独立运行的路由端 watchdog，由 watchdog 移除拦截规则并保留核心，避免 SSH 会话本身成为回滚执行者。

三个受控测试都会先在路由端执行 `sh -n`，再占用一个共享、原子的事务槽；若上一轮事务仍在，会明确拒绝重入。watchdog 使用每轮随机 token、PID、进程 starttime 和完整 argv 做身份校验，正常完成与超时回滚通过原子 action 文件仲裁。启动/防火墙测试的兜底窗口为 180 秒，boot 验证为 300 秒。

受控启动、防火墙和 boot 测试期间还会写入 `/tmp/d01-stability/maintenance`，完成或回滚后删除。若已经运行稳定性探针，这段计划内停核/切规则窗口不会被误存成一次真实故障触发。

若日志出现：

```text
can't open '/starts/fw_getlanip.sh'
```

说明调用防火墙脚本前没有设置并导出 `CRASHDIR=/data/ShellCrash`。使用本项目已修正的 payload，不要手工从 `/starts` 调用。

## 10. 安装 D01 自启服务和防火墙钩子

只有前九步全部成功后才运行：

```powershell
.\run.bat install_shellcrash_d01_boot.py
```

```bash
./run.sh install_shellcrash_d01_boot.py
```

成功标志：

```text
D01_AUTOSTART_ENABLED_AND_VALIDATED
CONTROLLER_API_HTTP=401
FINAL_SHELLCRASH_FIREWALL_REFS=>0
CLIENT_CONNECTIVITY_HTTP_STATUS=204
```

面板已安装且可达时才额外打印 `DASHBOARD_READY=http://192.168.31.1:9999/ui/`；它不是自启成功的必要条件。

所有 preflight 失败都发生在服务/路由测试之前：重复运行已经完成的 boot 安装器不会为了“回滚”而停掉健康服务。boot 验证全程保留 `.dis_startup` 持久安全锁，并通过专用 `test_start` 路径启动；只有核心、规则、Controller、客户端联网和 watchdog 释放全部验证成功后，才把删除安全锁作为最后提交。

安装内容：

```text
/etc/rc.d/S95shellcrash_d01 -> ../init.d/shellcrash_d01
/etc/rc.d/K10shellcrash_d01 -> ../init.d/shellcrash_d01
/data/shellcrash_firewall_hook.sh
```

最后进入 [重启验收](06-VERIFY.md)。
