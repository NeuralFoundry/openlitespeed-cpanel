[English](../../README.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [Português](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | **한국어** | [Bahasa Indonesia](README.id.md)

# OpenLiteSpeed for cPanel and WHM

웹사이트: [openlitespeed.dev/cpanel-whm](https://openlitespeed.dev/cpanel-whm/)

**olscp**는 cPanel용 OpenLiteSpeed 도구로, cPanel/WHM 서버에서 Apache를 [OpenLiteSpeed](https://openlitespeed.org)로 그대로 대체합니다. 기존 Apache 설정과 cPanel 계정 데이터를 읽어 OpenLiteSpeed 설정을 생성하고, 자동으로 동기화 상태를 유지하며, 모든 것을 관리할 수 있도록 WHM 플러그인과 cPanel 플러그인을 추가합니다. GPL-3.0으로 배포되는 무료 오픈 소스입니다.

![olscp WHM 플러그인 대시보드](../dashboard.png)

## 기능

- cPanel을 그대로 사용할 수 있습니다: 계정, 애드온 도메인, 서브도메인, 파킹 도메인, AutoSSL, 계정 정지, MultiPHP, `restartsrv_httpd`, chkservd, EasyApache 업데이트
- 안전한 전환: 전환 후 모든 사이트를 HTTP와 HTTPS로 확인하고, Apache에서 동작하던 사이트가 하나라도 OpenLiteSpeed에서 실패하면 서버가 자동으로 Apache로 롤백됩니다. 드라이 런은 Apache가 계속 서비스하는 동안 미리 보기 포트에서 모든 사이트를 먼저 확인합니다
- `httpd.conf`와 모든 include 파일을 읽으므로 사용자 지정 Apache 설정과 추가 가상 호스트도 그대로 옮겨집니다
- `.htaccess` 지원: 리라이트 규칙, Directory Privacy, Require/Allow/Deny, 헤더, expires, 리디렉션, 오류 페이지, MIME 유형, `SetEnvIf`를 이용한 봇 차단, `php_value`, `<FilesMatch>` 안의 캐시 헤더(WP Rocket, W3 Total Cache), 디렉터리별 PHP 버전
- 실시간 `.htaccess`: 리라이트 변경 사항이 재시작 없이 1초 안에 적용됩니다. 미리 빌드된 패치 바이너리 또는 서버에서 컴파일한 바이너리를 사용합니다
- PHP는 cPanel PHP-FPM 풀 또는 계정별 LSAPI로 실행되며, detached 모드라서 재시작해도 OPcache가 유지됩니다
- cPanel Application Manager와 CloudLinux 셀렉터의 Node.js, Python, Ruby 애플리케이션을 OpenLiteSpeed가 계정 사용자로 실행합니다
- 켜면 PHP와 애플리케이션에 CloudLinux LVE와 CageFS가 적용됩니다
- 사이트별 저장소를 쓰는 LSCache, WordPress 캐시 관리, 최종 사용자용 cPanel 플러그인
- cPanel/OWASP 규칙 세트를 사용하는 ModSecurity
- WordPress 무차별 대입 공격 방어, 봇 요청 속도 제한, 사용자 또는 패키지별 cgroups v2 리소스 제한
- 도메인별로 끌 수 있는 HTTP/3 (QUIC), Brotli, IPv6, 캐시 적중률과 애플리케이션 풀 사용량을 보여 주는 실시간 통계, 8080/8443 포트의 미리 보기 모드
- WHM 플러그인에서 클릭 한 번으로 업데이트

## 요구 사항

- cPanel & WHM 11.130 이상
- AlmaLinux, Rocky Linux 또는 CloudLinux 8 또는 9, x86_64
- EasyApache 4 PHP 버전

## 설치

```bash
git clone https://github.com/NeuralFoundry/openlitespeed-cpanel.git
cd openlitespeed-cpanel
bash install.sh
```

설치 프로그램은 공식 LiteSpeed 저장소에서 OpenLiteSpeed를 내려받아 `keys/`에 고정된 GPG 키로 검증하고, EasyApache의 모든 PHP 버전에 `lsphp`를 설치한 다음 WHM 플러그인을 등록합니다. 전환하기 전까지는 Apache가 계속 서비스합니다.

1. 선택 사항인 드라이 런: 대시보드에서 **Dry run**을 클릭하거나 `olscp dry-run`을 실행합니다. OpenLiteSpeed가 8080/8443 포트에서 시작되고 Apache가 계속 서비스하는 동안 모든 사이트를 확인합니다. 문제가 생길 사이트가 있다면 어떤 사이트인지 볼 수 있습니다.
2. 전환: **WHM > Plugins > OpenLiteSpeed**를 열고 **Switch to OpenLiteSpeed**를 클릭하거나 `olscp enable`를 실행합니다. 전환 후 모든 사이트를 확인하고, Apache에서 동작하던 사이트가 하나라도 실패하면 서버가 자동으로 Apache로 롤백됩니다. 일부 사이트가 실패해도 OpenLiteSpeed를 유지하려면 `olscp enable --no-rollback`을 사용합니다.
3. 언제든 Apache로 돌아가려면: `olscp disable`.

`rpms.litespeedtech.com`에 접근할 수 없는 서버는 로컬 패키지로 설치할 수 있습니다:

```bash
OLSCP_OLS_RPM=/root/openlitespeed-1.9.4-2.el9.x86_64.rpm bash install.sh
```

## 실시간 .htaccess

기본 OpenLiteSpeed 바이너리는 `.htaccess` 리라이트 규칙을 한 번만 읽습니다. olscp에는 작은 패치(`build/patches/`)가 포함되어 있어, 변경된 리라이트 규칙을 1초 안에 다시 읽고 새 `.htaccess` 파일을 첫 요청에서 감지하며 재시작이 필요 없습니다. 그 밖의 지시어는 그레이스풀 재시작으로 자동 적용됩니다.

각 릴리스에는 EL8과 EL9용 패치 바이너리가 들어 있습니다. olscp는 릴리스에서 이를 내려받아 `build/prebuilt.txt`의 SHA-256으로 확인한 뒤 전환합니다:

```bash
olscp ols fetch --use  # download the prebuilt binary and switch to it
olscp ols build        # or compile it on the server in the background, about 10 minutes
olscp ols use olscp    # switch to a compiled build, "olscp ols use official" switches back
```

컴파일할 때는 `dnf`로 툴체인을 설치하고 고정된 커밋의 OpenLiteSpeed 소스를 GitHub에서 가져옵니다. 설치할 때 미리 빌드된 바이너리를 받으려면 `OLSCP_FETCH_OLS=1 bash install.sh`를 실행합니다. 같은 작업은 WHM 플러그인의 **Version** 페이지에서도 할 수 있습니다.

![olscp가 가져온 Apache 설정](../apache.png)

## 업데이트

WHM 플러그인의 **Version** 페이지는 최신 릴리스를 보여 주고 클릭 한 번으로 olscp를 업데이트합니다. 업데이트는 GitHub에서 릴리스를 내려받아 설치 프로그램을 실행하고 OpenLiteSpeed를 그레이스풀하게 다시 로드합니다. olscp가 이전에 내려받은 미리 빌드된 바이너리는 새 릴리스의 바이너리로 교체됩니다.

![WHM 플러그인의 미리 빌드된 바이너리와 업데이트](../version.png)

```bash
olscp update check     # look for a new release
olscp update start     # update in the background, log in /var/log/olscp-update.log
```

## 명령줄

| 명령 | 설명 |
|---|---|
| `olscp status` | 서버, 감시 프로세스, 동기화 상태 |
| `olscp enable` / `olscp disable` | OpenLiteSpeed로 전환 / Apache로 복귀 |
| `olscp restart` | 설정을 다시 생성하고 그레이스풀하게 재시작 |
| `olscp apache report` | Apache 설정에서 읽은 설정 |
| `olscp htaccess report` | 적용하지 못한 `.htaccess` 지시어 |
| `olscp apps` / `olscp apps restart --vhost example.com --uri /` | Node.js, Python, Ruby 애플리케이션 / 하나 재시작 |
| `olscp cache list` / `olscp cache purge --all` | LSCache 사이트 / 캐시 비우기 |
| `olscp ols versions` / `olscp ols upgrade` | OpenLiteSpeed 버전과 업그레이드 |
| `olscp ols fetch --use` | 실시간 `.htaccess`용 미리 빌드된 바이너리를 내려받아 사용 |
| `olscp update check` / `olscp update start` | 새 olscp 릴리스 확인 / 업데이트 |
| `olscp settings key=value --apply` | 설정 변경 |

## Node.js, Python, Ruby 애플리케이션

olscp는 cPanel Application Manager가 Apache 설정에 쓰고 CloudLinux Node.js 및 Python 셀렉터가 `.htaccess`에 쓰는 Passenger 설정을 읽습니다: `PassengerAppRoot`, `PassengerBaseURI`, `PassengerAppType`, `PassengerStartupFile`, `PassengerNodejs`, `PassengerPython`, `PassengerRuby`, `PassengerAppEnv`, `PassengerAppLogFile`, `SetEnv`. 각 애플리케이션은 계정 사용자로 실행되고, 첫 요청에서 시작되며, 서버를 재시작해도 계속 실행됩니다.

고객은 계속 **cPanel > Application Manager**에서 애플리케이션을 등록합니다:

![cPanel Application Manager에 등록된 애플리케이션](../app-manager.png)

**cPanel > Application Status**는 고객 자신의 애플리케이션을 보여 주고, 재시작하고, 로그를 보여 줍니다:

![cPanel의 Application Status](../app-status.png)

![cPanel의 애플리케이션 로그](../app-log.png)

WHM 플러그인의 **Apps** 페이지는 모든 계정의 애플리케이션을 상태, 인터프리터, 로그 파일, 재시작 버튼과 함께 보여 줍니다:

![WHM 플러그인의 Node.js, Python, Ruby 애플리케이션](../apps.png)

- Node.js 애플리케이션은 OpenLiteSpeed Node.js 스타터로 실행됩니다. `listen()` 호출은 OpenLiteSpeed가 애플리케이션에 할당한 소켓으로 리디렉션됩니다.
- Python 애플리케이션은 `libexec/lswsgi.py`로 실행됩니다. 이는 Python 3.6 이상의 모든 인터프리터나 가상 환경에서 동작하는 작은 WSGI 서버입니다. 시작 파일은 `application`을 정의해야 합니다(기본값 `passenger_wsgi.py`).
- Ruby 애플리케이션은 `libexec/lsrack.rb`로 실행됩니다. 이는 Ruby 2.5 이상용 작은 Rack 서버입니다. 애플리케이션에 `Gemfile`이 있으면 Bundler로 `config.ru`를 로드하므로, 로컬 경로를 지정한 `bundle install`도 동작합니다. 애플리케이션에 `rack` gem이 설치되어 있어야 합니다. `RACK_ENV`와 `RAILS_ENV`는 `PassengerAppEnv`를 따릅니다.
- 애플리케이션을 재시작하려면 애플리케이션 루트의 `tmp/restart.txt`를 touch하거나 **cPanel > Application Status** 또는 **WHM > Plugins > OpenLiteSpeed > Apps**를 사용합니다. 설정이 바뀌면 자동으로 재시작됩니다.
- 출력은 애플리케이션 루트의 `stderr.log`에 기록되며, `PassengerAppLogFile`이 홈 디렉터리 안에 있으면 그 파일에 기록됩니다.
- 애플리케이션 URI 아래에 있는 문서 루트의 하위 디렉터리는 Passenger와 마찬가지로 정적 파일로 제공됩니다. `/.well-known/`은 AutoSSL을 위해 계속 접근할 수 있습니다.
- 애플리케이션 유형은 `PassengerAppType`이 설정되지 않은 경우 시작 파일(`passenger_wsgi.py`, `app.js`, `config.ru`)로 정해집니다. Node.js, Python, Ruby를 가리키지 않는 인터프리터 경로는 시스템 인터프리터로 바뀝니다.
- 애플리케이션 루트는 계정 홈 디렉터리 안에 있어야 합니다. Apache 설정에 cPanel 기본값인 `PassengerDisableHtaccess on`이 있으면 `.htaccess`의 Passenger 설정은 무시됩니다.

## 디렉터리별 PHP 버전

MultiPHP는 도메인의 PHP 버전을 `AddHandler application/x-httpd-ea-phpXX` 형태로 `.htaccess`에 씁니다. 하위 디렉터리가 도메인과 다른 버전을 사용하면, olscp는 그 디렉터리의 PHP 파일을 해당 계정의 그 버전 LSAPI 프로세스에 매핑하므로 Apache에서와 같이 버전이 적용됩니다. 이를 위해서는 LSAPI PHP 모드와 해당 버전의 LSAPI 패키지가 필요하며, 둘 다 WHM 플러그인의 **PHP** 페이지에 있습니다.

## FilesMatch의 캐시 헤더

WP Rocket, W3 Total Cache 같은 캐시 플러그인은 일부 파일 형식에 헤더나 만료 시간만 설정하는 `<FilesMatch>` 블록을 `.htaccess`에 씁니다. olscp는 각 블록을 해당 디렉터리의 접근 규칙, PHP 설정, 리라이트 규칙을 유지하는 정규식 컨텍스트로 바꿉니다. 그래서 존재하지 않는 `sitemap.xml` 요청도 여전히 WordPress에 도달하고, 보호된 디렉터리는 계속 보호됩니다.

## CloudLinux

CloudLinux에서 OpenLiteSpeed는 PHP와 애플리케이션을 계정의 LVE 안에서 시작할 수 있고, CageFS가 설치되어 있으면 그 CageFS 안에서 시작할 수 있습니다. 기본값은 꺼짐이며, CloudLinux가 감지되면 대시보드에 표시됩니다. **Settings > CloudLinux**(Auto, LVE, LVE and CageFS)에서 켜거나 `olscp settings cloudlinux=auto --apply`로 켭니다. olscp는 `/etc/cagefs/conf.d/olscp.cfg`로 자체 파일을 CageFS에 추가하고, `cagefsctl --update`를 실행한 다음 PHP와 애플리케이션 프로세스를 재시작합니다. 이후 리소스 제한은 LVE Manager에서 관리하며 olscp의 cgroups v2 제한은 꺼집니다.

## 제거

```bash
bash uninstall.sh          # switch back to Apache, remove the plugins and services
bash uninstall.sh --purge  # also delete /usr/local/olscp, settings, cache and logs
```

## 제한 사항

- `.htaccess`에서 변환되지 않는 항목: `<If>`, `Require host/expr`, `AuthType Digest`, 헤더와 만료 시간 외의 설정도 하는 `<FilesMatch>` 블록.
- Ruby 애플리케이션은 WebSocket이나 `rack.hijack`을 사용할 수 없습니다.
- CloudLinux 지원은 OpenLiteSpeed에 내장된 LVE 및 CageFS 훅을 사용합니다. `liblve` 대체 구현으로 테스트했으며, 라이선스가 있는 CloudLinux 서버에서는 아직 테스트하지 않았습니다.
- cPanel FPM 풀이 `doc_root`를 제한하기 때문에 PHP-FPM을 쓰는 사이트에서는 디렉터리 목록을 사용할 수 없습니다. LSAPI에서는 동작합니다.
- 전용 IP에서 SNI를 지원하지 않는 클라이언트는 서버 인증서를 받습니다.
- 릴리스 아카이브는 서명되어 있지 않습니다. 업데이트는 GitHub와의 HTTPS 연결에 의존하며, 미리 빌드된 바이너리는 `build/prebuilt.txt`의 SHA-256으로도 확인합니다.

## 기여하기

버그 보고와 풀 리퀘스트를 환영합니다. [CONTRIBUTING.md](../../CONTRIBUTING.md)를 참고하세요. 보안 문제는 [SECURITY.md](../../SECURITY.md)에 설명된 대로 비공개로 알려 주세요.

## 라이선스

GPL-3.0, [LICENSE](../../LICENSE)를 참고하세요. OpenLiteSpeed는 LiteSpeed Technologies가 개발하며 GPL-3.0으로 라이선스됩니다. `build/patches/`의 패치도 같은 라이선스로 배포됩니다. 이 프로젝트는 LiteSpeed Technologies 또는 cPanel, L.L.C.와 제휴 관계가 없으며 이들의 보증을 받지 않았습니다. LiteSpeed, OpenLiteSpeed, LSCache, cPanel, WHM은 각 소유자의 상표입니다.

같은 저자의 다른 프로젝트: [OpenLiteSpeed for Windows](https://github.com/NeuralFoundry/openlitespeed-windows), OpenLiteSpeed의 네이티브 Windows 빌드입니다.
