# 参考资料

## 漏洞与 SSH 入口

- THALIUM，Rooting Xiaomi WiFi Routers：<https://blog.thalium.re/posts/rooting-xiaomi-wifi-routers/>
- NVD，CVE-2023-26319：<https://nvd.nist.gov/vuln/detail/CVE-2023-26319>
- Xiaomi Security Center，CVE-2023-26319 公告：<https://trust.mi.com/misrc/bulletins/advisory?cveId=536>
- XMiR-Patcher：<https://github.com/openwrt-xiaomi/xmir-patcher>
- XMiR-Patcher 固定基线中的 D01 型号表：<https://github.com/openwrt-xiaomi/xmir-patcher/blob/16a46e350e3de2cb3415ab2cb652df53783998dc/xqmodel.py>

### XMiR-Patcher 平台入口

- 固定基线 README（Windows `run.bat`、Linux/macOS `run.sh`）：<https://github.com/openwrt-xiaomi/xmir-patcher/blob/16a46e350e3de2cb3415ab2cb652df53783998dc/README.md>
- 固定基线 `run.sh`：<https://github.com/openwrt-xiaomi/xmir-patcher/blob/16a46e350e3de2cb3415ab2cb652df53783998dc/run.sh>
- 固定基线 Python 依赖：<https://github.com/openwrt-xiaomi/xmir-patcher/blob/16a46e350e3de2cb3415ab2cb652df53783998dc/requirements.txt>

本项目补丁将该 `run.sh` 的 GNU `find -wholename` 包检测改为 Python import 检测，以避免 macOS BSD `find` 不兼容；Linux/macOS 路径目前仍标记为待实机复演。

## ShellCrash、Mihomo 与面板

- ShellCrash：<https://github.com/juewuy/ShellCrash>
- ShellCrash releases：<https://github.com/juewuy/ShellCrash/releases>
- Mihomo v1.19.28 release：<https://github.com/MetaCubeX/mihomo/releases/tag/v1.19.28>
- Mihomo DNS 文档：<https://wiki.metacubex.one/config/dns/>
- Mihomo TUN 文档：<https://wiki.metacubex.one/config/inbound/tun/>
- Mihomo 路由规则文档：<https://wiki.metacubex.one/config/rules/>
- Zashboard：<https://github.com/Zephyruso/zashboard>

## 本项目的实测结论与上游事实如何区分

- “SmartController 存在命令注入”来自漏洞研究和 CVE；
- “XMiR 能与小米路由器交互并利用相关入口”来自 XMiR-Patcher；
- “D01 1.0.72 上原流程只稳定得到 Telnet、需要 ARMv7 回退和 legacy init”是本项目实测；
- “D01 没有可用 TUN/TPROXY”是对该设备内核和实际规则插入的实测，不应外推到所有 D01 ROM；
- “Redir + redir-host + UDP 直连”通过启动、流量和重启验收。后续使用出现过间歇断网，故障原因尚未确认；
- DNS `#策略组` 语法来自 Mihomo 官方文档，具体域名与策略属于用户配置。
