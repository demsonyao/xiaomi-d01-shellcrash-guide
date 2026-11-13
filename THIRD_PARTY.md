# 上游组件、版本与再分发边界

本仓库默认不提交第三方二进制，只提交 D01 适配脚本、补丁、文档、来源和校验值。

| 组件 | 本次基线 | 上游 | 许可证/说明 |
|---|---|---|---|
| XMiR-Patcher | commit `16a46e350e3de2cb3415ab2cb652df53783998dc` | https://github.com/openwrt-xiaomi/xmir-patcher | 仓库页面未发现明确根许可证文件；因此公开包只发布针对固定 commit 的补丁，不镜像整个项目 |
| ShellCrash | `1.9.4release` | https://github.com/juewuy/ShellCrash | GPL-3.0；本项目使用本地审阅后的框架归档 |
| Mihomo | `v1.19.28` ARMv7 UPX | https://github.com/MetaCubeX/mihomo/releases/tag/v1.19.28 | GPL-3.0；本地 UPX 重打包文件的 SHA 与官方 gzip 资产不同 |
| Zashboard | 可选本地离线面板包 | https://github.com/Zephyruso/zashboard | MIT |
| 漏洞研究 | CVE-2023-26319 | https://blog.thalium.re/posts/rooting-xiaomi-wifi-routers/ | 研究归 Julien R.、Marin Duroyon；本项目不声称发现该漏洞 |

## 本次实际使用的本地资产

| 文件 | 字节 | SHA256 |
|---|---:|---|
| `ShellCrash.tar.gz` | 123627 | `4f946031a0483ed528e266143d459075489cce6c3f8f2f4681f39ca6d7448681` |
| `mihomo-shellcrash-armv7.upx` | 10185476 | `33d58f2103c674caaf12ac350cd351539102b6089fae0a3ce44b50fb36f86b64` |
| `zashboard.tar.gz` | 848404 | `a16e688c6774ae0bc17ec7364fb8c8825b752a65afe8ff5be3dffddea96c2128` |

框架和内核可以从以下固定地址获取，下载后与表中的 SHA256 比对：

- [ShellCrash 1.9.4 发行归档](https://github.com/juewuy/ShellCrash/releases/download/1.9.4/ShellCrash.tar.gz)，保存为 `ShellCrash.tar.gz`。
- [ShellCrash 上游仓库的固定 ARMv7 UPX 构建](https://raw.githubusercontent.com/juewuy/ShellCrash/ffe9f8c0dbd0708b808f1a9e6dc92f21453cec93/bin/meta/clash-linux-armv7.upx)，保存为 `cores/mihomo-shellcrash-armv7.upx`。

可选面板使用当时准备的离线归档，表中的校验值用于识别该归档。只有框架和内核就可以完成主流程。
