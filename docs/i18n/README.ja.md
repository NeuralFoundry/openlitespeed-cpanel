[English](../../README.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [Português](README.pt-BR.md) | [Русский](README.ru.md) | **日本語** | [Deutsch](README.de.md) | [Français](README.fr.md) | [한국어](README.ko.md) | [Bahasa Indonesia](README.id.md)

# OpenLiteSpeed for cPanel and WHM

Web サイト: [openlitespeed.dev/cpanel-whm](https://openlitespeed.dev/cpanel-whm/)

**olscp** は cPanel 用の OpenLiteSpeed 導入ツールで、cPanel/WHM サーバー上で [OpenLiteSpeed](https://openlitespeed.org) を Apache のドロップイン置き換えとして動かします。既存の Apache 設定と cPanel のアカウント情報を読み取って OpenLiteSpeed の設定を生成し、自動で同期を保ちます。すべてを管理するための WHM プラグインと cPanel プラグインも追加します。GPL-3.0 の無料オープンソースです。

![olscp WHM プラグインのダッシュボード](../dashboard.png)

## 機能

- cPanel をそのまま使えます: アカウント、アドオンドメイン、サブドメイン、パークドメイン、AutoSSL、アカウントの停止、MultiPHP、`restartsrv_httpd`、chkservd、EasyApache の更新
- 安全な切り替え: 切り替え後にすべてのサイトを HTTP と HTTPS で確認し、Apache で動いていたサイトが OpenLiteSpeed で 1 つでも失敗すると、サーバーは自動で Apache に戻ります。ドライランでは、Apache が配信を続けたまま、先にプレビュー用ポートで全サイトを確認します
- `httpd.conf` とすべての include ファイルを読み取るため、独自の Apache 設定や追加のバーチャルホストも引き継がれます
- `.htaccess` 対応: リライトルール、Directory Privacy、Require/Allow/Deny、ヘッダー、expires、リダイレクト、エラーページ、MIME タイプ、`SetEnvIf` によるボットのブロック、`php_value`、`<FilesMatch>` 内のキャッシュヘッダー (WP Rocket、W3 Total Cache)、ディレクトリごとの PHP バージョン
- ライブ `.htaccess`: リライトの変更は再起動なしで 1 秒以内に反映されます。ビルド済みのパッチ適用バイナリか、サーバー上でコンパイルしたバイナリを使います
- PHP はアカウントごとの cPanel PHP-FPM プールまたは LSAPI で動作し、detached モードのため再起動しても OPcache が保持されます
- cPanel Application Manager と CloudLinux のセレクターで登録された Node.js、Python、Ruby アプリを、OpenLiteSpeed がアカウントのユーザーとして起動します
- 有効にすると、PHP とアプリに CloudLinux LVE と CageFS を適用します
- サイトごとのストレージを持つ LSCache、WordPress のキャッシュ管理、エンドユーザー向けの cPanel プラグイン
- cPanel/OWASP ルールセットを使う ModSecurity
- WordPress のブルートフォース対策、ボットのレート制限、ユーザーまたはパッケージごとの cgroups v2 リソース制限
- ドメインごとに無効化できる HTTP/3 (QUIC)、Brotli、IPv6、キャッシュヒット率とアプリケーションプールの使用状況を含むリアルタイム統計、ポート 8080/8443 のプレビューモード
- WHM プラグインからのワンクリック更新

## 動作要件

- cPanel & WHM 11.130 以降
- AlmaLinux、Rocky Linux または CloudLinux 8 か 9、x86_64
- EasyApache 4 の PHP バージョン

## インストール

```bash
git clone https://github.com/NeuralFoundry/openlitespeed-cpanel.git
cd openlitespeed-cpanel
bash install.sh
```

インストーラーは公式の LiteSpeed リポジトリから OpenLiteSpeed をダウンロードし、`keys/` に固定された GPG 鍵で検証して、EasyApache の各 PHP バージョン用に `lsphp` をインストールし、WHM プラグインを登録します。切り替えるまでは Apache が配信を続けます。

1. 任意のドライラン: ダッシュボードで **Dry run** をクリックするか、`olscp dry-run` を実行します。OpenLiteSpeed がポート 8080/8443 で起動し、Apache が配信を続けたまま全サイトを確認します。動かなくなるサイトがあれば、どのサイトかが表示されます。
2. 切り替え: **WHM > Plugins > OpenLiteSpeed** を開いて **Switch to OpenLiteSpeed** をクリックするか、`olscp enable` を実行します。切り替え後に全サイトを確認し、Apache で動いていたサイトが 1 つでも失敗すると、サーバーは自動で Apache に戻ります。一部のサイトが失敗しても OpenLiteSpeed のままにするには `olscp enable --no-rollback` を使います。
3. いつでも Apache に戻すには: `olscp disable`。

`rpms.litespeedtech.com` に接続できないサーバーでは、ローカルのパッケージからインストールできます:

```bash
OLSCP_OLS_RPM=/root/openlitespeed-1.9.4-2.el9.x86_64.rpm bash install.sh
```

## ライブ .htaccess

標準の OpenLiteSpeed バイナリは `.htaccess` のリライトルールを 1 回しか読み込みません。olscp には小さなパッチ (`build/patches/`) が含まれており、変更されたリライトルールを 1 秒以内に再読み込みし、新しい `.htaccess` ファイルも最初のリクエストで検出するので、再起動は不要です。その他のディレクティブはグレースフルリスタートで自動的に適用されます。

各リリースには EL8 と EL9 向けのパッチ適用バイナリが含まれています。olscp はリリースからそれをダウンロードし、`build/prebuilt.txt` の SHA-256 で確認してから切り替えます:

```bash
olscp ols fetch --use  # download the prebuilt binary and switch to it
olscp ols build        # or compile it on the server in the background, about 10 minutes
olscp ols use olscp    # switch to a compiled build, "olscp ols use official" switches back
```

コンパイル時には `dnf` でツールチェーンをインストールし、固定したコミットの OpenLiteSpeed ソースを GitHub から取得します。インストール時にビルド済みバイナリを取得するには、`OLSCP_FETCH_OLS=1 bash install.sh` を実行します。同じ操作は WHM プラグインの **Version** ページにもあります。

![olscp が取り込んだ Apache 設定](../apache.png)

## 更新

WHM プラグインの **Version** ページには最新リリースが表示され、ワンクリックで olscp を更新できます。更新では GitHub からリリースをダウンロードし、そのインストーラーを実行して、OpenLiteSpeed をグレースフルに再読み込みします。olscp が以前にダウンロードしたビルド済みバイナリは、新しいリリースのものに置き換えられます。

![WHM プラグインのビルド済みバイナリと更新](../version.png)

```bash
olscp update check     # look for a new release
olscp update start     # update in the background, log in /var/log/olscp-update.log
```

## コマンドライン

| コマンド | 説明 |
|---|---|
| `olscp status` | サーバー、ウォッチャー、同期の状態 |
| `olscp enable` / `olscp disable` | OpenLiteSpeed に切り替え / Apache に戻す |
| `olscp restart` | 設定を再生成してグレースフルに再起動 |
| `olscp apache report` | Apache 設定から読み取った設定 |
| `olscp htaccess report` | 適用できなかった `.htaccess` ディレクティブ |
| `olscp apps` / `olscp apps restart --vhost example.com --uri /` | Node.js、Python、Ruby アプリ / 1 つを再起動 |
| `olscp cache list` / `olscp cache purge --all` | LSCache のサイト / パージ |
| `olscp ols versions` / `olscp ols upgrade` | OpenLiteSpeed のバージョンとアップグレード |
| `olscp ols fetch --use` | ライブ `.htaccess` のビルド済みバイナリをダウンロードして使用 |
| `olscp update check` / `olscp update start` | olscp の新しいリリースを確認 / 更新 |
| `olscp settings key=value --apply` | 設定を変更 |

## Node.js、Python、Ruby アプリ

olscp は、cPanel Application Manager が Apache 設定に書き込む Passenger 設定と、CloudLinux の Node.js セレクターおよび Python セレクターが `.htaccess` に書き込む Passenger 設定を読み取ります: `PassengerAppRoot`、`PassengerBaseURI`、`PassengerAppType`、`PassengerStartupFile`、`PassengerNodejs`、`PassengerPython`、`PassengerRuby`、`PassengerAppEnv`、`PassengerAppLogFile`、`SetEnv`。各アプリはアカウントのユーザーとして動作し、最初のリクエストで起動して、サーバーを再起動しても動き続けます。

顧客は引き続き **cPanel > Application Manager** でアプリを登録します:

![cPanel Application Manager に登録されたアプリ](../app-manager.png)

**cPanel > Application Status** では、顧客が自分のアプリを確認し、再起動し、ログを見ることができます:

![cPanel の Application Status](../app-status.png)

![cPanel のアプリログ](../app-log.png)

WHM プラグインの **Apps** ページには、全アカウントのアプリが状態、インタープリター、ログファイル、再起動ボタンとともに一覧表示されます:

![WHM プラグインの Node.js、Python、Ruby アプリ](../apps.png)

- Node.js アプリは OpenLiteSpeed の Node.js スターターで動作します。`listen()` の呼び出しは、OpenLiteSpeed がアプリに割り当てたソケットにリダイレクトされます。
- Python アプリは `libexec/lswsgi.py` で動作します。これは Python 3.6 以降の任意のインタープリターや仮想環境で動く小さな WSGI サーバーです。スタートアップファイルでは `application` を定義する必要があります (デフォルトは `passenger_wsgi.py`)。
- Ruby アプリは `libexec/lsrack.rb` で動作します。これは Ruby 2.5 以降向けの小さな Rack サーバーです。アプリに `Gemfile` がある場合は Bundler で `config.ru` を読み込むため、ローカルパスを指定した `bundle install` も使えます。アプリ用に `rack` gem をインストールしておく必要があります。`RACK_ENV` と `RAILS_ENV` は `PassengerAppEnv` に従います。
- アプリを再起動するには、アプリのルートにある `tmp/restart.txt` を touch するか、**cPanel > Application Status** または **WHM > Plugins > OpenLiteSpeed > Apps** を使います。設定を変更すると自動で再起動します。
- 出力はアプリのルートにある `stderr.log` に書き込まれます。`PassengerAppLogFile` がホームディレクトリ内にある場合はそちらに書き込まれます。
- アプリの URI 配下にあるドキュメントルートのサブディレクトリは、Passenger と同じく静的ファイルとして配信されます。`/.well-known/` は AutoSSL のためにアクセス可能なままです。
- アプリの種類は、`PassengerAppType` が設定されていなければスタートアップファイル (`passenger_wsgi.py`、`app.js`、`config.ru`) から判断します。Node.js、Python、Ruby を指していないインタープリターのパスは、システムのものに置き換えられます。
- アプリのルートはアカウントのホームディレクトリ内になければなりません。Apache 設定に cPanel のデフォルトである `PassengerDisableHtaccess on` がある場合、`.htaccess` 内の Passenger 設定は無視されます。

## ディレクトリごとの PHP バージョン

MultiPHP は、ドメインの PHP バージョンを `AddHandler application/x-httpd-ea-phpXX` として `.htaccess` に書き込みます。サブディレクトリがドメインと異なるバージョンを使う場合、olscp はそのディレクトリの PHP ファイルを、そのアカウントの該当バージョンの LSAPI プロセスに割り当てます。これにより、Apache と同じようにバージョンが適用されます。これには LSAPI の PHP モードと該当バージョンの LSAPI パッケージが必要で、どちらも WHM プラグインの **PHP** ページにあります。

## FilesMatch 内のキャッシュヘッダー

WP Rocket や W3 Total Cache などのキャッシュプラグインは、一部のファイル形式に対してヘッダーや有効期限だけを設定する `<FilesMatch>` ブロックを `.htaccess` に書き込みます。olscp は各ブロックを、そのディレクトリのアクセスルール、PHP 設定、リライトルールを保持した正規表現コンテキストに変換します。そのため、存在しない `sitemap.xml` へのリクエストも WordPress に届き、保護されたディレクトリは保護されたままです。

## CloudLinux

CloudLinux では、OpenLiteSpeed は PHP とアプリをアカウントの LVE 内で起動でき、CageFS がインストールされていればその CageFS 内で起動できます。デフォルトではオフで、CloudLinux が検出されるとダッシュボードに表示されます。**Settings > CloudLinux** (Auto、LVE、LVE and CageFS) か `olscp settings cloudlinux=auto --apply` で有効にします。olscp は `/etc/cagefs/conf.d/olscp.cfg` で自身のファイルを CageFS に追加し、`cagefsctl --update` を実行して、PHP とアプリのプロセスを再起動します。その後はリソース制限を LVE Manager が管理し、olscp の cgroups v2 制限はオフになります。

## アンインストール

```bash
bash uninstall.sh          # switch back to Apache, remove the plugins and services
bash uninstall.sh --purge  # also delete /usr/local/olscp, settings, cache and logs
```

## 制限事項

- `.htaccess` から変換されないもの: `<If>`、`Require host/expr`、`AuthType Digest`、ヘッダーと有効期限以外も設定する `<FilesMatch>` ブロック。
- Ruby アプリでは WebSocket や `rack.hijack` を使えません。
- CloudLinux 対応には OpenLiteSpeed に組み込まれた LVE と CageFS のフックを使います。`liblve` の代替実装でテストしており、ライセンスのある CloudLinux サーバーではまだテストしていません。
- cPanel の FPM プールは `doc_root` を制限するため、PHP-FPM のサイトではディレクトリ一覧を表示できません。LSAPI では使えます。
- 専用 IP 上の SNI 非対応クライアントには、サーバー証明書が返されます。
- リリースアーカイブには署名がありません。更新は GitHub への HTTPS 接続に依存します。ビルド済みバイナリは `build/prebuilt.txt` の SHA-256 でも確認されます。

## コントリビュート

バグ報告とプルリクエストを歓迎します。[CONTRIBUTING.md](../../CONTRIBUTING.md) をご覧ください。セキュリティの問題は [SECURITY.md](../../SECURITY.md) に記載の方法で非公開で報告してください。

## ライセンス

GPL-3.0 です。[LICENSE](../../LICENSE) をご覧ください。OpenLiteSpeed は LiteSpeed Technologies が開発し、GPL-3.0 でライセンスされています。`build/patches/` のパッチも同じライセンスで配布されます。このプロジェクトは LiteSpeed Technologies および cPanel, L.L.C. とは関係がなく、承認も受けていません。LiteSpeed、OpenLiteSpeed、LSCache、cPanel、WHM は各所有者の商標です。

同じ作者によるプロジェクト: [OpenLiteSpeed for Windows](https://github.com/NeuralFoundry/openlitespeed-windows)。OpenLiteSpeed のネイティブ Windows ビルドです。
