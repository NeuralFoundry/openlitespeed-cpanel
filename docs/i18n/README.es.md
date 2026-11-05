[English](../../README.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | **Español** | [Português](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [한국어](README.ko.md) | [Bahasa Indonesia](README.id.md)

# OpenLiteSpeed for cPanel and WHM

Sitio web: [openlitespeed.dev/cpanel-whm](https://openlitespeed.dev/cpanel-whm/)

**olscp** lleva OpenLiteSpeed a cPanel: ejecuta [OpenLiteSpeed](https://openlitespeed.org) en servidores cPanel/WHM como reemplazo directo de Apache. Lee la configuración existente de Apache y los datos de las cuentas de cPanel, genera la configuración de OpenLiteSpeed, la mantiene sincronizada automáticamente y añade un plugin de WHM y un plugin de cPanel para gestionarlo todo. Es gratuito y de código abierto bajo la licencia GPL-3.0.

![Panel del plugin de WHM de olscp](../dashboard.png)

## Características

- Funciona con cPanel tal como está: cuentas, dominios adicionales, subdominios y dominios aparcados, AutoSSL, suspensiones, MultiPHP, `restartsrv_httpd`, chkservd y actualizaciones de EasyApache
- Cambio seguro: después del cambio se comprueba cada sitio por HTTP y HTTPS, y el servidor vuelve automáticamente a Apache si algún sitio que funcionaba con Apache falla con OpenLiteSpeed. Una prueba en seco (dry run) comprueba antes cada sitio en los puertos de vista previa mientras Apache sigue sirviendo
- Lee `httpd.conf` y todos sus includes, así que los ajustes personalizados de Apache y los virtual hosts adicionales se conservan
- Soporte de `.htaccess`: reglas de reescritura, Directory Privacy, Require/Allow/Deny, cabeceras, expires, redirecciones, páginas de error, tipos MIME, bloqueo de bots con `SetEnvIf`, `php_value`, cabeceras de caché en `<FilesMatch>` (WP Rocket, W3 Total Cache) y una versión de PHP distinta por directorio
- `.htaccess` en vivo: los cambios de reescritura se aplican en menos de un segundo sin reiniciar, con un binario parcheado precompilado o uno compilado en el servidor
- PHP mediante los pools PHP-FPM de cPanel o LSAPI por cuenta, en modo detached para que los reinicios conserven OPcache
- Aplicaciones Node.js, Python y Ruby de cPanel Application Manager y de los selectores de CloudLinux, iniciadas por OpenLiteSpeed con el usuario de la cuenta
- CloudLinux LVE y CageFS para PHP y aplicaciones, cuando se activa
- LSCache con almacenamiento por sitio, gestión de la caché de WordPress y un plugin de cPanel para los usuarios finales
- ModSecurity con los conjuntos de reglas de cPanel/OWASP
- Protección de WordPress contra fuerza bruta, limitación de velocidad para bots y límites de recursos con cgroups v2 por usuario o paquete
- HTTP/3 (QUIC) con una lista de dominios donde desactivarlo, Brotli, IPv6, estadísticas en tiempo real con la tasa de aciertos de caché y el uso de los pools de aplicaciones, y un modo de vista previa en los puertos 8080/8443
- Actualizaciones con un clic desde el plugin de WHM

## Requisitos

- cPanel & WHM 11.130 o posterior
- AlmaLinux, Rocky Linux o CloudLinux 8 o 9, x86_64
- Versiones de PHP de EasyApache 4

## Instalación

```bash
git clone https://github.com/NeuralFoundry/openlitespeed-cpanel.git
cd openlitespeed-cpanel
bash install.sh
```

El instalador descarga OpenLiteSpeed del repositorio oficial de LiteSpeed, lo verifica con las claves GPG fijadas en `keys/`, instala `lsphp` para cada versión de PHP de EasyApache y registra el plugin de WHM. Apache sigue sirviendo hasta que usted haga el cambio.

1. Prueba en seco opcional: haga clic en **Dry run** en el panel o ejecute `olscp dry-run`. OpenLiteSpeed arranca en los puertos 8080/8443 y se comprueba cada sitio mientras Apache sigue sirviendo; verá qué sitios fallarían, si hay alguno.
2. Cambio: abra **WHM > Plugins > OpenLiteSpeed** y haga clic en **Switch to OpenLiteSpeed**, o ejecute `olscp enable`. Después del cambio se comprueba cada sitio y el servidor vuelve automáticamente a Apache si falla algún sitio que funcionaba con Apache. Use `olscp enable --no-rollback` para mantener OpenLiteSpeed aunque fallen algunos sitios.
3. Para volver a Apache en cualquier momento: `olscp disable`.

Los servidores que no pueden acceder a `rpms.litespeedtech.com` pueden instalar desde un paquete local:

```bash
OLSCP_OLS_RPM=/root/openlitespeed-1.9.4-2.el9.x86_64.rpm bash install.sh
```

## .htaccess en vivo

El binario estándar de OpenLiteSpeed carga las reglas de reescritura de `.htaccess` una sola vez. olscp incluye un pequeño parche (`build/patches/`) que recarga las reglas de reescritura modificadas en menos de un segundo y detecta los archivos `.htaccess` nuevos en la primera petición, sin reiniciar. Las demás directivas se aplican automáticamente con un reinicio ordenado (graceful restart).

Cada versión publicada incluye el binario parcheado para EL8 y EL9. olscp lo descarga de la versión, lo comprueba con el SHA-256 de `build/prebuilt.txt` y pasa a usarlo:

```bash
olscp ols fetch --use  # download the prebuilt binary and switch to it
olscp ols build        # or compile it on the server in the background, about 10 minutes
olscp ols use olscp    # switch to a compiled build, "olscp ols use official" switches back
```

La compilación instala las herramientas de compilación con `dnf` y descarga el código fuente de OpenLiteSpeed desde GitHub en commits fijados. Para obtener el binario precompilado durante la instalación, ejecute `OLSCP_FETCH_OLS=1 bash install.sh`. Las mismas acciones están en la página **Version** del plugin de WHM.

![Configuración de Apache importada por olscp](../apache.png)

## Actualizaciones

La página **Version** del plugin de WHM muestra la última versión y actualiza olscp con un clic. La actualización descarga la versión desde GitHub, ejecuta su instalador y recarga OpenLiteSpeed de forma ordenada. Si olscp descargó antes un binario precompilado, se sustituye por el de la nueva versión.

![Binario precompilado y actualizaciones en el plugin de WHM](../version.png)

```bash
olscp update check     # look for a new release
olscp update start     # update in the background, log in /var/log/olscp-update.log
```

## Línea de comandos

| Comando | Descripción |
|---|---|
| `olscp status` | Estado del servidor, del watcher y de la sincronización |
| `olscp enable` / `olscp disable` | Cambiar a OpenLiteSpeed / volver a Apache |
| `olscp restart` | Regenera la configuración y reinicia de forma ordenada |
| `olscp apache report` | Ajustes leídos de la configuración de Apache |
| `olscp htaccess report` | Directivas de `.htaccess` que no se pudieron aplicar |
| `olscp apps` / `olscp apps restart --vhost example.com --uri /` | Aplicaciones Node.js, Python y Ruby / reiniciar una |
| `olscp cache list` / `olscp cache purge --all` | Sitios con LSCache / purgar la caché |
| `olscp ols versions` / `olscp ols upgrade` | Versión de OpenLiteSpeed y actualización |
| `olscp ols fetch --use` | Descarga el binario precompilado con `.htaccess` en vivo y lo usa |
| `olscp update check` / `olscp update start` | Buscar una nueva versión de olscp / actualizar |
| `olscp settings key=value --apply` | Cambia un ajuste |

## Aplicaciones Node.js, Python y Ruby

olscp lee los ajustes de Passenger que cPanel Application Manager escribe en la configuración de Apache y que los selectores de Node.js y Python de CloudLinux escriben en `.htaccess`: `PassengerAppRoot`, `PassengerBaseURI`, `PassengerAppType`, `PassengerStartupFile`, `PassengerNodejs`, `PassengerPython`, `PassengerRuby`, `PassengerAppEnv`, `PassengerAppLogFile` y `SetEnv`. Cada aplicación se ejecuta con el usuario de la cuenta, se inicia con la primera petición y sigue en marcha tras los reinicios del servidor.

Los clientes siguen usando **cPanel > Application Manager** para registrar sus aplicaciones:

![Aplicaciones registradas en cPanel Application Manager](../app-manager.png)

**cPanel > Application Status** muestra las aplicaciones del propio cliente, las reinicia y muestra su log:

![Application Status en cPanel](../app-status.png)

![Log de una aplicación en cPanel](../app-log.png)

La página **Apps** del plugin de WHM lista las aplicaciones de todas las cuentas con su estado, intérprete, archivo de log y un botón de reinicio:

![Aplicaciones Node.js, Python y Ruby en el plugin de WHM](../apps.png)

- Las aplicaciones Node.js se ejecutan con el iniciador de Node.js de OpenLiteSpeed. Las llamadas a `listen()` se redirigen al socket que OpenLiteSpeed asigna a la aplicación.
- Las aplicaciones Python se ejecutan con `libexec/lswsgi.py`, un pequeño servidor WSGI que funciona con cualquier intérprete o entorno virtual de Python 3.6 o posterior. El archivo de inicio debe definir `application` (por defecto `passenger_wsgi.py`).
- Las aplicaciones Ruby se ejecutan con `libexec/lsrack.rb`, un pequeño servidor Rack para Ruby 2.5 o posterior. Carga `config.ru` con Bundler cuando la aplicación tiene un `Gemfile`, así que `bundle install` con una ruta local funciona. La gema `rack` debe estar instalada para la aplicación. `RACK_ENV` y `RAILS_ENV` siguen a `PassengerAppEnv`.
- Para reiniciar una aplicación, actualice con touch `tmp/restart.txt` en la raíz de la aplicación, o use **cPanel > Application Status** o **WHM > Plugins > OpenLiteSpeed > Apps**. Los cambios de ajustes la reinician automáticamente.
- La salida va a `stderr.log` en la raíz de la aplicación, o a `PassengerAppLogFile` cuando está dentro del directorio personal.
- Los subdirectorios de la raíz de documentos bajo la URI de la aplicación se sirven como archivos estáticos, igual que con Passenger. `/.well-known/` sigue accesible para AutoSSL.
- El tipo de aplicación se deduce del archivo de inicio (`passenger_wsgi.py`, `app.js` o `config.ru`) salvo que se defina `PassengerAppType`. Una ruta de intérprete que no apunte a Node.js, Python o Ruby se sustituye por la del sistema.
- La raíz de la aplicación debe estar dentro del directorio personal de la cuenta. Cuando la configuración de Apache tiene `PassengerDisableHtaccess on`, que es el valor por defecto de cPanel, se ignoran los ajustes de Passenger en `.htaccess`.

## Versión de PHP por directorio

MultiPHP escribe la versión de PHP de un dominio en `.htaccess` como `AddHandler application/x-httpd-ea-phpXX`. Cuando un subdirectorio usa una versión distinta a la de su dominio, olscp asigna los archivos PHP de ese directorio al proceso LSAPI de esa versión para la cuenta, de modo que la versión se aplica igual que con Apache. Esto requiere el modo PHP LSAPI y el paquete LSAPI de esa versión, ambos en la página **PHP** del plugin de WHM.

## Cabeceras de caché en FilesMatch

Los plugins de caché como WP Rocket y W3 Total Cache escriben en `.htaccess` bloques `<FilesMatch>` que solo definen cabeceras o tiempos de expiración para algunos tipos de archivo. olscp convierte cada bloque en un contexto regex que conserva las reglas de acceso, los ajustes de PHP y las reglas de reescritura de su directorio, así que la petición de un `sitemap.xml` que no existe sigue llegando a WordPress y los directorios protegidos siguen protegidos.

## CloudLinux

En CloudLinux, OpenLiteSpeed puede iniciar PHP y las aplicaciones dentro del LVE de la cuenta y, si CageFS está instalado, dentro de su CageFS. Está desactivado por defecto; el panel indica cuándo se detecta CloudLinux. Actívelo en **Settings > CloudLinux** (Auto, LVE, LVE and CageFS) o con `olscp settings cloudlinux=auto --apply`. olscp añade sus propios archivos a CageFS con `/etc/cagefs/conf.d/olscp.cfg`, ejecuta `cagefsctl --update` y reinicia los procesos de PHP y de las aplicaciones. A partir de ahí, los límites de recursos vienen de LVE Manager y los límites de cgroups v2 de olscp se desactivan.

## Desinstalación

```bash
bash uninstall.sh          # switch back to Apache, remove the plugins and services
bash uninstall.sh --purge  # also delete /usr/local/olscp, settings, cache and logs
```

## Limitaciones

- No se traducen desde `.htaccess`: `<If>`, `Require host/expr`, `AuthType Digest` y los bloques `<FilesMatch>` que definen algo más que cabeceras y tiempos de expiración.
- Las aplicaciones Ruby no pueden usar WebSockets ni `rack.hijack`.
- El soporte de CloudLinux usa los hooks de LVE y CageFS integrados en OpenLiteSpeed. Se probó con un sustituto de `liblve`, todavía no en un servidor CloudLinux con licencia.
- El listado de directorios no está disponible para sitios con PHP-FPM, porque los pools FPM de cPanel restringen `doc_root`. Funciona con LSAPI.
- Los clientes sin SNI en IP dedicadas reciben el certificado del servidor.
- Los archivos de las versiones no están firmados. Las actualizaciones dependen de la conexión HTTPS con GitHub; los binarios precompilados también se comprueban con el SHA-256 de `build/prebuilt.txt`.

## Contribuir

Los informes de errores y los pull requests son bienvenidos, consulte [CONTRIBUTING.md](../../CONTRIBUTING.md). Informe de los problemas de seguridad de forma privada como se describe en [SECURITY.md](../../SECURITY.md).

## Licencia

GPL-3.0, consulte [LICENSE](../../LICENSE). OpenLiteSpeed está desarrollado por LiteSpeed Technologies y tiene licencia GPL-3.0; el parche de `build/patches/` se distribuye con la misma licencia. Este proyecto no está afiliado a LiteSpeed Technologies ni a cPanel, L.L.C., ni cuenta con su respaldo. LiteSpeed, OpenLiteSpeed, LSCache, cPanel y WHM son marcas comerciales de sus respectivos propietarios.

Del mismo autor: [OpenLiteSpeed for Windows](https://github.com/NeuralFoundry/openlitespeed-windows), una compilación nativa de OpenLiteSpeed para Windows.
