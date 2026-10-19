# Android Tools Builder

使用 GitHub Actions 的 Ubuntu 标准运行器，从上游源码交叉编译供 **Android 10 及以上、ARM64** 原生 shell 使用的工具。

仓库中只保存 workflow、构建和发布脚本、版本校验清单及说明。NDK 下载、上游源码下载、编译、测试、打包、产物上传和 Release 发布均由 GitHub Actions 执行。

不重复打包手机通常已有的 `ls`、`cp`、`cat`、`grep` 等基础命令。

## 当前支持

| 工具 | 用途 | 构建功能 |
| --- | --- | --- |
| curl | 网络请求、下载、调试接口 | HTTPS、HTTP/2、IPv6、代理、gzip，内置 CA 证书 |
| jq | JSON 查询、过滤和格式化 | 静态链接 Oniguruma，支持正则表达式 |

默认构建 curl 和 jq，手动运行时也可以选择只构建 `curl`。
当前均使用 NDK 的 Bionic 静态库构建，产物不需要另带第三方 `.so`。
curl 暂不包含 HTTP/3、SSH/SFTP、Brotli、Zstd、国际化域名和 libpsl。
如需自定义 CA，使用 `--cacert /path/to/ca.pem`，无需关闭证书验证。

## 在 GitHub 上使用

1. 打开本仓库的 **Actions → Build Android ARM64 tools → Run workflow**。
2. 选择 `curl` 或 `curl jq`，默认构建全部已支持的工具。
3. 构建通过后，**Publish Android ARM64 release** 会自动发布到仓库的 **Releases**。
4. 在 Release 中下载完整工具包 `android-arm64-tools.tar.gz`，或单独的 `curl-android-arm64`、`jq-android-arm64`。工具包内的可执行文件位于 `bin/`。

修改 workflow、脚本、源码清单或构建说明并推送时，也会自动构建。仓库无需保存编译产物或工具链。

workflow 使用 `ubuntu-24.04` 标准运行器，执行编译、架构与依赖检查，以及 QEMU 下的 ARM64 程序测试。Actions Artifacts 保留 14 天；Release 附件独立保存。
公开仓库标准运行器的计算时间免费；存储另有额度。参见 [GitHub Actions 计费说明](https://docs.github.com/en/billing/concepts/product-billing/github-actions)。

## 在手机上运行

从电脑通过 adb 复制到 shell 可执行的目录：

```sh
adb shell mkdir -p /data/local/tmp/tools
adb push bin/. /data/local/tmp/tools/
adb shell chmod 755 /data/local/tmp/tools/curl
adb shell /data/local/tmp/tools/curl --version
adb shell /data/local/tmp/tools/curl -I https://example.com
```

若构建了 jq：

```sh
adb shell chmod 755 /data/local/tmp/tools/jq
adb shell /data/local/tmp/tools/jq --version
```

普通使用不需要 root，访问权限由运行程序的 shell 或应用决定。
不要在 `/sdcard` 中直接执行；可先存放在那里，再复制到有执行权限的目录。
在 Termux 中使用时，应放到其有执行权限的私有目录。

## Actions 的构建规则

每次运行均在 GitHub 提供的 Ubuntu 运行器上按以下顺序执行：

1. 检出仓库中的规则文件，并安装编译与测试依赖。
2. 按 `sources.json` 下载固定版本的 NDK、curl、OpenSSL、nghttp2、zlib 和 CA 数据；选择 jq 时同时下载 jq 源码。
3. 校验下载文件的散列值，再解压到该次运行的 `.work/`。
4. 执行 `scripts/build.sh`，使用 NDK 的 API 29 工具链编译 ARM64 静态程序。
5. 检查 AArch64 ELF 架构，并拒绝带动态解释器或动态库依赖的产物。
6. 通过 QEMU 运行 ARM64 程序，检查 curl 的 HTTPS/HTTP2 功能标记、可信和未知证书的处理，以及 jq 的 JSON 和正则功能。
7. 打包许可证、源码清单、工具和校验值，只有前面步骤均成功才上传到该次 Actions 运行的 Artifacts。
8. 独立的发布 workflow 接收成功事件，校验包及内部文件后自动发布 Release。

`dist/` 和 `.work/` 均被 `.gitignore` 排除，只在运行器上产生。
包名为 `android-arm64-tools.tar.gz`，附带整个包的 SHA-256 校验文件；运行摘要会列出目标平台和构建工具。
QEMU 测试不替代真机测试，Android DNS、SELinux、应用网络权限仍需在手机上确认。

## 自动发布 Release

`.github/workflows/release.yml` 在主分支构建成功后运行 `release/publish.py`。它只读取本仓库 `main` 分支上 `build.yml` 的成功构建，校验产物散列值，并将 Release 标签固定到对应的源码提交。

每次构建对应一个标签，例如 `android-arm64-build-1`。已经发布的同一构建会直接跳过；附件全部上传后才将草稿转为正式 Release。

Release 附件包括：

- `android-arm64-tools.tar.gz` 和对应的 `.sha256` 文件：完整工具包。
- `curl-android-arm64`、`jq-android-arm64`：本次实际构建的独立程序；只构建 curl 时不会包含 jq。
- `licenses.tar.gz`：独立程序对应的许可证、源码版本清单、CA 和使用说明。
- `SHA256SUMS`：所有附件的校验值。

下载独立程序后先执行 `chmod 755 文件名`，也可以将它改名为 `curl` 或 `jq`。校验全部附件可执行 `sha256sum -c SHA256SUMS`。

已有成功构建也能发布：在 **Actions → Publish Android ARM64 release → Run workflow** 中填写该次构建的数字 `run_id`（构建页面 URL 的最后一段）。该流程直接下载已有 Artifacts，不重新编译；对应产物需要尚未过期。

发布 workflow 使用内置 `GITHUB_TOKEN` 的 `actions: read` 和 `contents: write` 权限，无需额外配置 PAT。构建 workflow 仍然只有读取权限。

## 版本与证书更新

源码 URL、版本和校验值固定在 `sources.json`，构建时校验后才解压。
更新软件时同时更改 URL、版本、解压目录、文件名和上游校验值。
CA 包固定到 2026-09-25 版本并内置到 curl；需更新根证书时，更改其固定日期 URL、版本和校验值后重新编译。
它使用 Mozilla 公共根证书，不会自动采用 Android 用户安装的私有 CA。
发布包包含上游许可证、CA 文件、源码信息及 SHA256SUMS。

## 后续可补充的工具

| 工具 | 用途 |
| --- | --- |
| ripgrep (`rg`) | 递归文本搜索、忽略规则 |
| fd | 便捷的文件查找 |
| aria2 | 多连接下载、任务管理 |
| rsync | 增量同步、文件传输 |
| OpenSSH (`ssh` / `scp` / `sftp`) | 远程登录和传输 |
| sqlite3 | 查询、修改 SQLite 数据库 |
| yq | YAML 查询和转换 |
| zstd / xz / 7zz | 更完整的压缩与解压 |

此表是扩展候选，尚未加入构建脚本。Android 的基础命令并不与所有 GNU 选项一致，确有参数兼容需求时，再单独增加 GNU 工具。

构建依据：[curl Android 构建说明](https://curl.se/docs/install.html#Android)、[OpenSSL Android 说明](https://github.com/openssl/openssl/blob/openssl-3.5.9/NOTES-ANDROID.md)、[jq 源码](https://github.com/jqlang/jq)。
