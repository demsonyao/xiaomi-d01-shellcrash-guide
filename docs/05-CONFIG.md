# 自己的订阅、规则与 redir-host DNS

## 配置与公开代码必须物理分开

完整 YAML 通常包含节点服务器、UUID、密码、Reality public key、订阅特征和自定义规则。把它放在公开仓库外，例如：

```text
C:\Users\<YOU>\Documents\d01-private-recovery\inputs\config.yaml
$HOME/Documents/d01-private-recovery/inputs/config.yaml
```

公开仓库只保留 [示例片段](../examples/user-redir-host.example.yaml)。

`import_d01_full_yaml.py` 是 D01 兼容性门禁，不是恶意 YAML 沙箱。完整 Mihomo 配置可以引用 provider URL、下载源和外部服务，而核心以 root 身份运行；只导入自己审查过或可信供应方生成的配置，陌生订阅转换结果应先人工检查。`RAW_CONFIG_VALID` 只表示语法和本教程基线通过，不等于来源安全。

## D01 必需的 DNS 基线

```yaml
dns:
  enable: true
  listen: ':1053'
  ipv6: false
  enhanced-mode: redir-host
```

公开导入器会同时强制检查 `ipv6: false`；缺失或写成 `true` 都会在上传前停止。它会原样保留整个 DNS 子树（包括 `nameserver-policy` 和带 `#策略组` 的 DoH），并生成 ShellCrash 1.9.4 实际参与运行时合并的 DNS-only `user.yaml`；不会把节点、订阅或规则复制进这个 overlay。

不要保留：

```yaml
enhanced-mode: fake-ip
fake-ip-range: ...
fake-ip-filter: ...
```

原因不是 Fake-IP 本身“不安全”，而是本方案无法透明接管普通 UDP。游戏 UDP 直连时必须拿到真实目标 IP，才不会把 Fake-IP 地址直接发向公网。

## Controller 对 LAN 监听时必须认证

本教程的运行时使用：

```yaml
external-controller: ':9999'
```

这会让可信 LAN 能访问 Mihomo Controller，不论是否安装 Zashboard。因此必须设置一个唯一的 Controller secret。不要把真实值写入公开示例或 Git；`prepare_d01_runtime_redir_host.py` 会在缺失时隐藏询问并写入 ShellCrash 持久配置，随后要求未授权 `/version` 请求返回 HTTP 401。

HTTP 200 在其他只绑定 loopback 的部署中可能合理，但本教程固定监听 `:9999`，所以未授权 HTTP 200 会被视为认证缺失并触发停止/回滚。

Controller 与 Zashboard 在这套基线上使用可信 LAN 内的明文 HTTP。secret 能阻止未授权 API 调用，但不提供传输加密；请用密码管理器生成独立高熵值，只在自己的可信局域网中登录，不要做 WAN 端口转发。

## 境外 DoH 通过策略组发出

如果路由器直连境外 DoH 失败，Mihomo 可能对 X、Facebook 等域名返回 SERVFAIL。Mihomo 支持在 DNS 地址后追加 `#代理组名`：

```yaml
dns:
  default-nameserver:
    - 223.5.5.5
    - 119.29.29.29

  proxy-server-nameserver:
    - 223.5.5.5
    - 119.29.29.29

  nameserver-policy:
    '+.x.com': 'https://1.1.1.1/dns-query#你的策略组'
    '+.twitter.com': 'https://1.1.1.1/dns-query#你的策略组'
    '+.facebook.com': 'https://1.1.1.1/dns-query#你的策略组'
    '+.fbcdn.net': 'https://1.1.1.1/dns-query#你的策略组'
```

`#你的策略组` 的含义是：建立这条 DoH HTTPS 连接时，通过该 Mihomo 出站组发送。它不是把节点密码交给 Cloudflare，也不是改写 DNS 查询内容。

策略组名必须与 `proxy-groups` 中现有名称完全一致。公开示例不能硬编码某个用户的组名。

`proxy-server-nameserver` 用于先解析代理节点自己的域名，避免“需要代理才能解析代理服务器”的循环依赖。这里可使用能直连的可信解析器。

## 规则基线

至少保留局域网和保留地址直连：

```yaml
rules:
  - IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,172.16.0.0/12,DIRECT,no-resolve
  - IP-CIDR,192.168.0.0/16,DIRECT,no-resolve
  - IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
  - MATCH,你的策略组
```

真实生产规则由使用者自行维护。本项目不推荐把任何个人规则或订阅作为“官方默认”。

## UDP 的真实语义

即使节点条目写了 `udp: true`，在 D01 的 TCP Redir 方案里，LAN 普通 UDP 也不会自动进入该节点。`udp: true` 只说明节点协议本身能够承载 UDP；还需要 TUN/TPROXY 或显式代理入口把 UDP 交给 Mihomo，而本机内核缺少这条透明路径。

因此：

- 游戏 UDP：直连；
- QUIC/HTTP3：可能直连；
- TCP HTTPS：按规则进入 Redir；
- DNS：由路由/Mihomo 单独处理。

如需强制视频走 TCP，可选择阻断 QUIC，但这与本教程“UDP 直连”不是同一件事，且可能影响应用性能。

## 不要公开原实测 DNS 修复脚本

私人脚本 `repair_d01_foreign_dns.py` 针对特定策略组、固定替换数量和特定域名做了强校验，适合恢复这台机器，但不适合作为通用脚本。公开教程只保留上述原理和参数化示例。
