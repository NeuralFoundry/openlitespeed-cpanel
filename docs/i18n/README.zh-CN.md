[English](../../README.md) | [Türkçe](README.tr.md) | **简体中文** | [Español](README.es.md) | [Português](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [한국어](README.ko.md) | [Bahasa Indonesia](README.id.md)

# OpenLiteSpeed for cPanel and WHM

网站：[openlitespeed.dev/cpanel-whm](https://openlitespeed.dev/cpanel-whm/)

**olscp** 在 cPanel/WHM 服务器上用 [OpenLiteSpeed](https://openlitespeed.org) 直接替换 Apache，让 cPanel 也能使用 OpenLiteSpeed。它读取现有的 Apache 配置和 cPanel 账户数据，生成 OpenLiteSpeed 配置并自动保持同步，同时提供一个 WHM 插件和一个 cPanel 插件来管理所有功能。基于 GPL-3.0 免费开源。

![olscp WHM 插件仪表板](../dashboard.png)

## 功能

- 与 cPanel 原样兼容：账户、附加域名、子域名和停放域名、AutoSSL、账户暂停、MultiPHP、`restartsrv_httpd`、chkservd 以及 EasyApache 更新
- 安全切换：切换后会通过 HTTP 和 HTTPS 检查每个站点，只要有一个在 Apache 上正常的站点在 OpenLiteSpeed 上出错，服务器就会自动回滚到 Apache。试运行（dry run）会先在预览端口上检查每个站点，期间 Apache 继续提供服务
- 读取 `httpd.conf` 及其所有 include 文件，自定义的 Apache 设置和额外的虚拟主机都会一并迁移
- `.htaccess` 支持：重写规则、Directory Privacy、Require/Allow/Deny、响应头、Expires、重定向、错误页面、MIME 类型、用 `SetEnvIf` 屏蔽爬虫、`php_value`、`<FilesMatch>` 中的缓存头（WP Rocket、W3 Total Cache），以及按目录使用不同的 PHP 版本
- 实时 `.htaccess`：重写规则的修改在一秒内生效，无需重启，可使用预编译的补丁版二进制文件，也可以在服务器上自行编译
- PHP 通过 cPanel PHP-FPM 池或按账户运行的 LSAPI 执行，采用 detached 模式，重启时 OPcache 得以保留
- 来自 cPanel Application Manager 和 CloudLinux selector 的 Node.js、Python 和 Ruby 应用，由 OpenLiteSpeed 以账户用户身份启动
- 开启后，PHP 和应用可运行在 CloudLinux LVE 和 CageFS 中
- LSCache：每个站点独立存储，支持 WordPress 缓存管理，并提供面向终端用户的 cPanel 插件
- ModSecurity，使用 cPanel/OWASP 规则集
- WordPress 暴力破解防护、爬虫限速，以及按用户或套餐设置的 cgroups v2 资源限制
- HTTP/3 (QUIC)（可按域名关闭）、Brotli、IPv6、实时统计（含缓存命中率和应用池使用情况），以及 8080/8443 端口上的预览模式
- 在 WHM 插件中一键更新

## 系统要求

- cPanel & WHM 11.130 或更新版本
- AlmaLinux、Rocky Linux 或 CloudLinux 8 或 9，x86_64
- EasyApache 4 PHP 版本

## 安装

```bash
git clone https://github.com/NeuralFoundry/openlitespeed-cpanel.git
cd openlitespeed-cpanel
bash install.sh
```

安装程序从 LiteSpeed 官方仓库下载 OpenLiteSpeed，使用 `keys/` 中固定的 GPG 密钥进行校验，为每个 EasyApache PHP 版本安装 `lsphp`，并注册 WHM 插件。在你切换之前，Apache 会继续提供服务。

1. 可选的试运行：在仪表板上点击 **Dry run**，或运行 `olscp dry-run`。OpenLiteSpeed 会在 8080/8443 端口启动，并在 Apache 继续提供服务的同时检查每个站点；如果有站点会出问题，你可以看到是哪些。
2. 切换：打开 **WHM > Plugins > OpenLiteSpeed** 并点击 **Switch to OpenLiteSpeed**，或运行 `olscp enable`。切换后会检查每个站点，只要有一个在 Apache 上正常的站点出错，服务器就会自动回滚到 Apache。如果希望即使部分站点出错也继续使用 OpenLiteSpeed，请使用 `olscp enable --no-rollback`。
3. 随时切回 Apache：`olscp disable`。

无法访问 `rpms.litespeedtech.com` 的服务器可以从本地软件包安装：

```bash
OLSCP_OLS_RPM=/root/openlitespeed-1.9.4-2.el9.x86_64.rpm bash install.sh
```

## 实时 .htaccess

原版 OpenLiteSpeed 二进制文件只加载一次 `.htaccess` 重写规则。olscp 附带一个小补丁（`build/patches/`），可在一秒内重新加载已修改的重写规则，并在首次请求时发现新的 `.htaccess` 文件，无需重启。其他指令会通过平滑重启自动生效。

每个版本都提供适用于 EL8 和 EL9 的补丁版二进制文件。olscp 从发布页面下载它，用 `build/prebuilt.txt` 中的 SHA-256 校验后切换过去：

```bash
olscp ols fetch --use  # download the prebuilt binary and switch to it
olscp ols build        # or compile it on the server in the background, about 10 minutes
olscp ols use olscp    # switch to a compiled build, "olscp ols use official" switches back
```

编译时会用 `dnf` 安装工具链，并从 GitHub 获取固定提交的 OpenLiteSpeed 源码。如需在安装时获取预编译二进制文件，请运行 `OLSCP_FETCH_OLS=1 bash install.sh`。WHM 插件的 **Version** 页面也提供相同的操作。

![olscp 导入的 Apache 配置](../apache.png)

## 更新

WHM 插件的 **Version** 页面显示最新版本，并可一键更新 olscp。更新会从 GitHub 下载该版本，运行其安装程序，并平滑重新加载 OpenLiteSpeed。olscp 之前下载的预编译二进制文件会被替换为新版本中的二进制文件。

![WHM 插件中的预编译二进制文件和更新](../version.png)

```bash
olscp update check     # look for a new release
olscp update start     # update in the background, log in /var/log/olscp-update.log
```

## 命令行

| 命令 | 说明 |
|---|---|
| `olscp status` | 服务器、监视进程和同步状态 |
| `olscp enable` / `olscp disable` | 切换到 OpenLiteSpeed / 切回 Apache |
| `olscp restart` | 重新生成配置并平滑重启 |
| `olscp apache report` | 从 Apache 配置中读取的设置 |
| `olscp htaccess report` | 无法应用的 `.htaccess` 指令 |
| `olscp apps` / `olscp apps restart --vhost example.com --uri /` | Node.js、Python 和 Ruby 应用 / 重启其中一个 |
| `olscp cache list` / `olscp cache purge --all` | 使用 LSCache 的站点 / 清除缓存 |
| `olscp ols versions` / `olscp ols upgrade` | OpenLiteSpeed 版本与升级 |
| `olscp ols fetch --use` | 下载并使用预编译的实时 `.htaccess` 二进制文件 |
| `olscp update check` / `olscp update start` | 检查 olscp 新版本 / 更新 |
| `olscp settings key=value --apply` | 修改设置 |

## Node.js、Python 和 Ruby 应用

olscp 读取 cPanel Application Manager 写入 Apache 配置、以及 CloudLinux Node.js 和 Python selector 写入 `.htaccess` 的 Passenger 设置：`PassengerAppRoot`、`PassengerBaseURI`、`PassengerAppType`、`PassengerStartupFile`、`PassengerNodejs`、`PassengerPython`、`PassengerRuby`、`PassengerAppEnv`、`PassengerAppLogFile` 和 `SetEnv`。每个应用都以账户用户身份运行，在首次请求时启动，服务器重启后也会继续运行。

客户继续使用 **cPanel > Application Manager** 注册自己的应用：

![在 cPanel Application Manager 中注册的应用](../app-manager.png)

**cPanel > Application Status** 显示客户自己的应用，可以重启这些应用并查看日志：

![cPanel 中的 Application Status](../app-status.png)

![cPanel 中的应用日志](../app-log.png)

WHM 插件的 **Apps** 页面列出所有账户的应用，包括状态、解释器、日志文件和重启按钮：

![WHM 插件中的 Node.js、Python 和 Ruby 应用](../apps.png)

- Node.js 应用通过 OpenLiteSpeed 的 Node.js 启动器运行。对 `listen()` 的调用会被重定向到 OpenLiteSpeed 分配给该应用的 socket。
- Python 应用通过 `libexec/lswsgi.py` 运行，这是一个小型 WSGI 服务器，适用于任何 Python 3.6 或更新版本的解释器或虚拟环境。启动文件必须定义 `application`（默认 `passenger_wsgi.py`）。
- Ruby 应用通过 `libexec/lsrack.rb` 运行，这是一个适用于 Ruby 2.5 或更新版本的小型 Rack 服务器。如果应用有 `Gemfile`，它会通过 Bundler 加载 `config.ru`，因此使用本地路径的 `bundle install` 也能正常工作。必须为应用安装 `rack` gem。`RACK_ENV` 和 `RAILS_ENV` 跟随 `PassengerAppEnv`。
- 要重启应用，可以 touch 应用根目录下的 `tmp/restart.txt`，或使用 **cPanel > Application Status** 或 **WHM > Plugins > OpenLiteSpeed > Apps**。修改设置后应用会自动重启。
- 输出写入应用根目录下的 `stderr.log`；如果 `PassengerAppLogFile` 位于主目录内，则写入该文件。
- 与 Passenger 一样，应用 URI 下的文档根目录子目录作为静态文件提供。`/.well-known/` 对 AutoSSL 保持可访问。
- 除非设置了 `PassengerAppType`，否则应用类型由启动文件（`passenger_wsgi.py`、`app.js` 或 `config.ru`）决定。不指向 Node.js、Python 或 Ruby 的解释器路径会被替换为系统自带的解释器。
- 应用根目录必须位于账户主目录内。如果 Apache 配置中有 `PassengerDisableHtaccess on`（cPanel 默认如此），`.htaccess` 中的 Passenger 设置会被忽略。

## 按目录设置 PHP 版本

MultiPHP 会把域名的 PHP 版本以 `AddHandler application/x-httpd-ea-phpXX` 的形式写入 `.htaccess`。当某个子目录使用的版本与其域名不同时，olscp 会把该目录的 PHP 文件映射到该账户对应版本的 LSAPI 进程，使该版本像在 Apache 下一样生效。这需要 LSAPI PHP 模式和该版本的 LSAPI 软件包，两者都在 WHM 插件的 **PHP** 页面中。

## FilesMatch 中的缓存头

WP Rocket 和 W3 Total Cache 等缓存插件会在 `.htaccess` 中写入 `<FilesMatch>` 块，只为部分文件类型设置响应头或过期时间。olscp 将每个块转换为一个正则 context，并保留其所在目录的访问规则、PHP 设置和重写规则，因此对不存在的 `sitemap.xml` 的请求仍会到达 WordPress，受保护的目录也依然受到保护。

## CloudLinux

在 CloudLinux 上，OpenLiteSpeed 可以在账户的 LVE 中启动 PHP 和应用；如果安装了 CageFS，还会在账户的 CageFS 中启动。此功能默认关闭；检测到 CloudLinux 时，仪表板会显示提示。可以在 **Settings > CloudLinux**（Auto、LVE、LVE and CageFS）中开启，或使用 `olscp settings cloudlinux=auto --apply`。olscp 通过 `/etc/cagefs/conf.d/olscp.cfg` 将自己的文件加入 CageFS，运行 `cagefsctl --update`，并重启 PHP 和应用进程。此后资源限制由 LVE Manager 提供，olscp 的 cgroups v2 限制会被关闭。

## 卸载

```bash
bash uninstall.sh          # switch back to Apache, remove the plugins and services
bash uninstall.sh --purge  # also delete /usr/local/olscp, settings, cache and logs
```

## 限制

- 以下 `.htaccess` 内容不会被转换：`<If>`、`Require host/expr`、`AuthType Digest`，以及除响应头和过期时间外还设置了其他内容的 `<FilesMatch>` 块。
- Ruby 应用不能使用 WebSocket 或 `rack.hijack`。
- CloudLinux 支持使用 OpenLiteSpeed 内置的 LVE 和 CageFS 钩子。目前已用 `liblve` 的替代实现测试，尚未在已授权的 CloudLinux 服务器上测试。
- 使用 PHP-FPM 的站点无法使用目录列表，因为 cPanel FPM 池限制了 `doc_root`。使用 LSAPI 时可以。
- 在独立 IP 上不支持 SNI 的客户端会收到服务器证书。
- 发布归档没有签名。更新依赖与 GitHub 的 HTTPS 连接；预编译二进制文件还会用 `build/prebuilt.txt` 中的 SHA-256 校验。

## 参与贡献

欢迎提交错误报告和拉取请求，参见 [CONTRIBUTING.md](../../CONTRIBUTING.md)。安全问题请按照 [SECURITY.md](../../SECURITY.md) 中的说明私下报告。

## 许可证

GPL-3.0，参见 [LICENSE](../../LICENSE)。OpenLiteSpeed 由 LiteSpeed Technologies 开发，采用 GPL-3.0 许可证；`build/patches/` 中的补丁以相同的许可证分发。本项目与 LiteSpeed Technologies 或 cPanel, L.L.C. 无关联，也未获得其认可。LiteSpeed、OpenLiteSpeed、LSCache、cPanel 和 WHM 是其各自所有者的商标。

同一作者的其他项目：[OpenLiteSpeed for Windows](https://github.com/NeuralFoundry/openlitespeed-windows)，OpenLiteSpeed 的原生 Windows 版本。
