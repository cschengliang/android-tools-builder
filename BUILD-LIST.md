# 编译列表

由 `build-list.json` 和 `sources.json` 生成。

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

## 架构对照

| 架构标识 | Android ABI | 用途 |
| --- | --- | --- |
| `arm64` | `arm64-v8a` | 主流 64 位 ARM 手机和平板 |
| `armv7` | `armeabi-v7a` | 32 位 ARM 设备 |
| `x86_64` | `x86_64` | 64 位 x86 模拟器及设备 |
| `x86` | `x86` | 32 位 x86 模拟器及设备 |

## 功能

- **ripgrep**：Unicode、忽略规则、Rust 正则引擎。
- **stress**：经典 stress；附带对应源码。
- **curl**：HTTPS、HTTP/2、代理、gzip、内置 CA。
- **jq**：内置 Oniguruma 正则引擎。
- **iperf3**：客户端、服务端、JSON；不启用可选身份认证。
- **zstd**：多线程、校验、字典；不附带其他格式压缩库。
- **sqlite3**：FTS5、RTree、数学函数；禁用动态扩展加载。
- **socat**：TCP、UDP、Unix socket、OpenSSL；无 readline。
- **aria2**：HTTP/HTTPS、FTP、BitTorrent、JSON-RPC；需指定 CA 文件；无 SFTP/Metalink。
- **tcpdump**：内置静态 libpcap；实时抓包需要相应权限。
- **strace**：跟踪受 ptrace/SELinux 限制；无 libdw 栈回溯及跨位数解码。
- **stress-ng**：静态精简依赖；可用测试项取决于内核和权限。
- **busybox**：完整通用配置适配 Android；内置 ash、awk、vi、网络和归档工具；附实际命令清单与配置。

维护清单后执行 `python3 scripts/catalog.py write` 更新表格；Actions 会检查表格与规则一致。实际编译和发布均在 GitHub 运行器上执行。
