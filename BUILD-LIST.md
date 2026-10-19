# 编译列表

由 `build-list.json` 和 `sources.json` 生成。

| 工具 | 程序名 | 固定版本 | 用途 | arm64 | armv7 | x86_64 | x86 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [ripgrep](https://github.com/BurntSushi/ripgrep) | `rg` | 15.2.0 | 递归文本和正则搜索 | ✓ | ✓ | ✓ | ✓ |
| [stress](https://github.com/resurrecting-open-source-projects/stress) | `stress` | 1.0.7 | CPU、内存、I/O 和磁盘压力测试 | ✓ | ✓ | ✓ | ✓ |
| [curl](https://curl.se/) | `curl` | 8.23.0 | 网络请求、下载和接口调试 | ✓ | ✓ | ✓ | ✓ |

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

维护清单后执行 `python3 scripts/catalog.py write` 更新表格；Actions 会检查表格与规则一致。实际编译和发布均在 GitHub 运行器上执行。
