# Android Tools Builder

[![Build Android tools](https://github.com/cschengliang/android-tools-builder/actions/workflows/build.yml/badge.svg)](https://github.com/cschengliang/android-tools-builder/actions/workflows/build.yml)

用 GitHub Actions 从源码编译 Android 命令行工具，构建成功后自动发布到 [Releases](https://github.com/cschengliang/android-tools-builder/releases)。源码下载、编译、测试及发布均在 GitHub 运行器上完成。

## 编译列表

<!-- build-list:start -->
| 工具 | 程序名 | 固定版本 | 用途 | arm64 | armv7 | x86_64 | x86 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [ripgrep](https://github.com/BurntSushi/ripgrep) | `rg` | 15.2.0 | 递归文本和正则搜索 | ✓ | ✓ | ✓ | ✓ |
| [stress](https://github.com/resurrecting-open-source-projects/stress) | `stress` | 1.0.7 | CPU、内存、I/O 和磁盘压力测试 | ✓ | ✓ | ✓ | ✓ |
| [curl](https://curl.se/) | `curl` | 8.23.0 | 网络请求、下载和接口调试 | ✓ | ✓ | ✓ | ✓ |
| [jq](https://jqlang.org/) | `jq` | 1.8.2 | JSON 查询、过滤和转换 | ✓ | ✓ | ✓ | ✓ |
| [iperf3](https://software.es.net/iperf/) | `iperf3` | 3.22 | TCP/UDP 网络吞吐测试 | ✓ | ✓ | ✓ | ✓ |
| [zstd](https://github.com/facebook/zstd) | `zstd` | 1.5.7 | Zstandard 压缩和解压 | ✓ | ✓ | ✓ | ✓ |
| [sqlite3](https://sqlite.org/cli.html) | `sqlite3` | 3.54.1 | SQLite 数据库命令行 | ✓ | ✓ | ✓ | ✓ |
| [socat](https://github.com/dest-unreach/socat1) | `socat` | 1.8.1.3 | 网络转发和 socket 调试 | ✓ | ✓ | ✓ | ✓ |
| [aria2](https://github.com/aria2/aria2) | `aria2c` | 1.37.0 | 多连接下载和任务管理 | ✓ | ✓ | ✓ | ✓ |
| [tcpdump](https://www.tcpdump.org/) | `tcpdump` | 4.99.7 | 网络抓包和 pcap 分析 | ✓ | ✓ | ✓ | ✓ |
| [strace](https://strace.io/) | `strace` | 7.2 | 系统调用和信号跟踪 | ✓ | ✓ | ✓ | ✓ |
| [stress-ng](https://github.com/ColinIanKing/stress-ng) | `stress-ng` | 0.22.01 | CPU、内存及内核压力测试 | ✓ | ✓ | ✓ | ✓ |
| [busybox](https://busybox.net/) | `busybox` | 1.38.0 | 多命令 Unix 工具箱 | ✓ | ✓ | ✓ | ✓ |

✓ 表示纳入 Actions 构建和测试矩阵；成功结果以 Actions 和 Release 为准。所有架构面向 Android 10+（API 29），不要求额外第三方动态库。
<!-- build-list:end -->

完整的[编译列表和架构对照表](BUILD-LIST.md)由 `build-list.json` 和 `sources.json` 生成。当前默认构建表中的 13 项；`ripgrep` 的命令名是 `rg`，`aria2` 的命令名是 `aria2c`。`stress` 和 `stress-ng` 分别提供经典与扩展压力测试。

## 构建与下载

1. 进入 **Actions → Build Android tools → Run workflow**。
2. `tools` 和 `architectures` 默认为 `all`，会构建十三种工具 × 四种架构。
3. 也可填写部分组合，例如 `tools: ripgrep curl`、`architectures: arm64 x86_64`；支持空格或逗号分隔。
4. 全部选定架构的编译和测试通过后，**Publish Android release** 自动创建正式 Release。

每种架构有独立的包，例如 `android-arm64-tools.tar.gz`、`android-armv7-tools.tar.gz`、`android-x86_64-tools.tar.gz`、`android-x86-tools.tar.gz`。包内的 `bin/` 包含本次选择的程序。

Release 同时提供独立文件，例如 `rg-android-arm64`、`stress-android-armv7`、`curl-android-x86_64`。可通过 `SHA256SUMS` 或各架构的校验文件核对下载内容。需要随二进制分发的对应源码归档、构建规则和每种架构的许可证包也随 Release 提供。

## 架构与运行环境

统一基线为 **Android 10+（API 29）**。`arm64` 对应主流 ARM64 手机；`armv7` 用于 32 位 ARM 设备；`x86_64`、`x86` 用于对应的模拟器或设备。设备必须支持所选 ABI，64 位设备能否运行 32 位程序取决于系统。

程序使用 Android NDK 的 Bionic 静态库，避免携带额外第三方 `.so`。构建检查 ELF 架构、位数和动态依赖，再在 Linux x86 主机上直接运行 x86/x86_64 程序，并通过 QEMU 运行 ARM 程序。冒烟测试覆盖 HTTPS 证书校验与下载、JSON 和正则、SQL/FTS5、压缩往返、iperf3 TCP 传输、数据中继、离线 pcap 解码及有界压力任务。strace 仅测试启动和版本输出；真实 ptrace 跟踪及设备权限相关功能需要真机验证。

tcpdump 实时抓包和 strace 跟踪其他进程通常需要额外权限，并受 SELinux 约束。stress-ng 能运行的测试项取决于设备内核、权限和构建时可用功能。普通文件处理和网络客户端无需 root。

示例：将 ARM64 工具包的 `bin/` 复制到手机的 shell 可执行目录：

```sh
adb shell mkdir -p /data/local/tmp/tools
adb push bin/. /data/local/tmp/tools/
adb push cacert.pem /data/local/tmp/tools/
adb shell 'chmod 755 /data/local/tmp/tools/*'
adb shell /data/local/tmp/tools/rg --version
adb shell /data/local/tmp/tools/stress --version
adb shell /data/local/tmp/tools/curl --version
```

独立下载的文件可改名成 `rg`、`stress` 或 `curl` 后执行 `chmod 755 文件名`。Android 的共享存储（例如 `/sdcard`）通常没有执行权限，应复制到运行 shell 或应用允许执行的目录中。

## 维护规则

- `build-list.json`：启用的工具、程序名、依赖、Android API、Rust 版本和架构工具链映射。
- `sources.json`：固定的上游版本、源码 URL、文件名及校验值；下载验证后才解压。
- `scripts/build.sh`：按工具和架构交叉编译。
- `scripts/catalog.py`：生成编译表格和 Actions 矩阵。
- `release/publish.py`：校验成功构建的产物并自动发布。

修改清单或版本后执行 `python3 scripts/catalog.py write` 更新此表和 `BUILD-LIST.md`；该命令只生成文档，不编译程序。Actions 会检查文档是否与清单一致。构建规则变更推送到 `main` 后自动运行；默认四个架构并行，任一失败时不会发布不完整 Release。

curl 包含 HTTPS、HTTP/2、IPv6、代理、gzip 和内置 Mozilla CA；暂不包含 HTTP/3、SSH/SFTP、Brotli、Zstd、国际化域名或 libpsl。ripgrep 使用 Rust 正则引擎，暂不启用可选 PCRE2。CA 为固定日期快照，需要时更新其 URL、日期和校验值；私有 CA 可用 `curl --cacert` 指定。

aria2 包含 HTTP/HTTPS、FTP、BitTorrent 和 JSON-RPC；暂不包含 SFTP、Metalink、XML-RPC 和 c-ares 异步 DNS。HTTPS 下载请显式指定工具包中的证书文件，例如 `aria2c --ca-certificate=/data/local/tmp/tools/cacert.pem https://example.com/file`，私有服务改用自己的 CA；不关闭证书验证。单独下载 aria2c 时，还应下载 Release 附件中的 `cacert.pem`。sqlite3 禁用动态扩展加载；iperf3 不启用可选的 OpenSSL 身份认证。

## 自动发布

### BusyBox 完整配置

BusyBox 1.38.0 从上游完整通用 `defconfig` 开始适配 Android，保留内置 ash/hush、
awk、sed、vi、归档、网络及进程工具。它是一份独立静态 bin，不依赖 Termux 安装。
编译明确关闭不适用于 Android 账户模型的传统账户管理、PAM、utmp/wtmp、SunRPC
及外部 SELinux 库等功能；最终启用情况以各架构的实际配置和命令清单为准。

只构建 BusyBox 时在 Actions 填入 `tools: busybox`、`architectures: all`。
Release 的 `busybox-android-架构` 是可执行文件，另附：

- `busybox-applets-android-架构.txt`：与实际 `busybox --list` 一致的命令列表。
- `busybox-config-android-架构.txt`：实际编译 `.config`，也通过内置 `bbconfig` 提供。
- `busybox-build-android-架构.json`：命令数量、配置基线和关闭功能的原因。

```sh
chmod 755 busybox-android-arm64
./busybox-android-arm64 --list
./busybox-android-arm64 ash
./busybox-android-arm64 awk '{print $1}' data.txt
```

临时目录默认适配 `/data/local/tmp`，需要时设置 `TMPDIR`；守护进程可显式指定
工作目录、端口和配置。内置 applet 不代表设备内核及权限支持其全部操作。
BusyBox 的内置简化 TLS 实现不提供完整证书验证；需要验证 HTTPS 证书时使用
本仓库的 curl。详细构建说明也放在工具包的 `busybox/README.txt` 中。

### 发布流程

发布流程只接受本仓库 `main` 分支上 `build.yml` 的成功构建。每次构建对应 `android-tools-build-构建编号` 标签，并固定到实际构建的源码提交。全部附件上传完后才将草稿转成正式 Release；重复发布同一构建会跳过。

过去的成功构建也可从 **Actions → Publish Android release → Run workflow** 填入数字 `run_id` 发布，直接复用未过期的 Artifacts。Actions Artifacts 保留 14 天；Release 附件独立保存。发布用内置 `GITHUB_TOKEN`，无需 PAT；编译任务仅有读取权限。

使用公开仓库的标准 Ubuntu 运行器。[GitHub Actions 计费说明](https://docs.github.com/en/billing/concepts/product-billing/github-actions)中的存储额度仍适用。仓库只保存规则、清单、测试和说明，`.work/` 与 `dist/` 不进入 Git。
