[English](../../README.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [Português](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | **Français** | [한국어](README.ko.md) | [Bahasa Indonesia](README.id.md)

# OpenLiteSpeed for cPanel and WHM

Site web : [openlitespeed.dev/cpanel-whm](https://openlitespeed.dev/cpanel-whm/)

Avec **olscp**, vous utilisez OpenLiteSpeed sur cPanel : olscp fait tourner [OpenLiteSpeed](https://openlitespeed.org) sur les serveurs cPanel/WHM comme remplaçant direct d'Apache. Il lit la configuration Apache existante et les données des comptes cPanel, génère la configuration OpenLiteSpeed, la garde synchronisée automatiquement et ajoute un plugin WHM et un plugin cPanel pour tout gérer. Gratuit et open source sous licence GPL-3.0.

![Tableau de bord du plugin WHM d'olscp](../dashboard.png)

## Fonctionnalités

- Fonctionne avec cPanel tel quel : comptes, domaines supplémentaires (addon), sous-domaines et domaines parqués, AutoSSL, suspensions, MultiPHP, `restartsrv_httpd`, chkservd et mises à jour d'EasyApache
- Bascule sécurisée : après la bascule, chaque site est vérifié en HTTP et en HTTPS, et le serveur revient automatiquement à Apache si un site qui fonctionnait sous Apache échoue sous OpenLiteSpeed. Un test à blanc (dry run) vérifie d'abord chaque site sur les ports de prévisualisation pendant qu'Apache continue de servir
- Lit `httpd.conf` et tous les fichiers inclus, pour que les réglages Apache personnalisés et les hôtes virtuels supplémentaires soient repris
- Prise en charge de `.htaccess` : règles de réécriture, Directory Privacy, Require/Allow/Deny, en-têtes, expires, redirections, pages d'erreur, types MIME, blocage des bots avec `SetEnvIf`, `php_value`, en-têtes de cache dans `<FilesMatch>` (WP Rocket, W3 Total Cache) et une version de PHP différente par répertoire
- `.htaccess` en direct : les modifications de réécriture s'appliquent en moins d'une seconde sans redémarrage, avec un binaire patché précompilé ou un binaire compilé sur le serveur
- PHP via les pools PHP-FPM de cPanel ou LSAPI par compte, en mode detached pour que les redémarrages conservent OPcache
- Applications Node.js, Python et Ruby issues de cPanel Application Manager et des sélecteurs CloudLinux, lancées par OpenLiteSpeed sous l'utilisateur du compte
- CloudLinux LVE et CageFS pour PHP et les applications, une fois activés
- LSCache avec un stockage par site, la gestion du cache WordPress et un plugin cPanel pour les utilisateurs finaux
- ModSecurity avec les jeux de règles cPanel/OWASP
- Protection de WordPress contre la force brute, limitation de débit des bots et limites de ressources cgroups v2 par utilisateur ou par package
- HTTP/3 (QUIC) avec une liste de domaines où il est désactivé, Brotli, IPv6, statistiques en temps réel avec taux de succès du cache et utilisation des pools d'applications, et un mode de prévisualisation sur les ports 8080/8443
- Mises à jour en un clic depuis le plugin WHM

## Prérequis

- cPanel & WHM 11.130 ou plus récent
- AlmaLinux, Rocky Linux ou CloudLinux 8 ou 9, x86_64
- Versions de PHP d'EasyApache 4

## Installation

```bash
git clone https://github.com/NeuralFoundry/openlitespeed-cpanel.git
cd openlitespeed-cpanel
bash install.sh
```

L'installateur télécharge OpenLiteSpeed depuis le dépôt officiel de LiteSpeed, le vérifie avec les clés GPG épinglées dans `keys/`, installe `lsphp` pour chaque version de PHP d'EasyApache et enregistre le plugin WHM. Apache continue de servir jusqu'à ce que vous fassiez la bascule.

1. Test à blanc facultatif : cliquez sur **Dry run** dans le tableau de bord ou lancez `olscp dry-run`. OpenLiteSpeed démarre sur les ports 8080/8443 et chaque site est vérifié pendant qu'Apache continue de servir ; vous voyez quels sites ne fonctionneraient plus, s'il y en a.
2. Bascule : ouvrez **WHM > Plugins > OpenLiteSpeed** et cliquez sur **Switch to OpenLiteSpeed**, ou lancez `olscp enable`. Chaque site est vérifié après la bascule et le serveur revient automatiquement à Apache si un site qui fonctionnait sous Apache échoue. Utilisez `olscp enable --no-rollback` pour garder OpenLiteSpeed même si certains sites échouent.
3. Pour revenir à Apache à tout moment : `olscp disable`.

Les serveurs qui ne peuvent pas joindre `rpms.litespeedtech.com` peuvent installer depuis un paquet local :

```bash
OLSCP_OLS_RPM=/root/openlitespeed-1.9.4-2.el9.x86_64.rpm bash install.sh
```

## .htaccess en direct

Le binaire OpenLiteSpeed standard ne charge les règles de réécriture de `.htaccess` qu'une seule fois. olscp inclut un petit patch (`build/patches/`) qui recharge les règles de réécriture modifiées en moins d'une seconde et détecte les nouveaux fichiers `.htaccess` à la première requête, sans redémarrage. Les autres directives sont appliquées automatiquement avec un redémarrage en douceur (graceful restart).

Chaque version publiée contient le binaire patché pour EL8 et EL9. olscp le télécharge depuis la version, le vérifie avec le SHA-256 de `build/prebuilt.txt` et bascule dessus :

```bash
olscp ols fetch --use  # download the prebuilt binary and switch to it
olscp ols build        # or compile it on the server in the background, about 10 minutes
olscp ols use olscp    # switch to a compiled build, "olscp ols use official" switches back
```

La compilation installe la chaîne d'outils avec `dnf` et récupère les sources d'OpenLiteSpeed sur GitHub à des commits épinglés. Pour obtenir le binaire précompilé dès l'installation, lancez `OLSCP_FETCH_OLS=1 bash install.sh`. Les mêmes actions se trouvent sur la page **Version** du plugin WHM.

![Configuration Apache importée par olscp](../apache.png)

## Mises à jour

La page **Version** du plugin WHM affiche la dernière version et met à jour olscp en un clic. La mise à jour télécharge la version depuis GitHub, exécute son installateur et recharge OpenLiteSpeed en douceur. Un binaire précompilé téléchargé auparavant par olscp est remplacé par celui de la nouvelle version.

![Binaire précompilé et mises à jour dans le plugin WHM](../version.png)

```bash
olscp update check     # look for a new release
olscp update start     # update in the background, log in /var/log/olscp-update.log
```

## Ligne de commande

| Commande | Description |
|---|---|
| `olscp status` | État du serveur, du watcher et de la synchronisation |
| `olscp enable` / `olscp disable` | Basculer vers OpenLiteSpeed / revenir à Apache |
| `olscp restart` | Régénère la configuration et redémarre en douceur |
| `olscp apache report` | Réglages lus dans la configuration Apache |
| `olscp htaccess report` | Directives `.htaccess` qui n'ont pas pu être appliquées |
| `olscp apps` / `olscp apps restart --vhost example.com --uri /` | Applications Node.js, Python et Ruby / en redémarrer une |
| `olscp cache list` / `olscp cache purge --all` | Sites avec LSCache / purger le cache |
| `olscp ols versions` / `olscp ols upgrade` | Version d'OpenLiteSpeed et mise à niveau |
| `olscp ols fetch --use` | Télécharge le binaire précompilé avec `.htaccess` en direct et l'utilise |
| `olscp update check` / `olscp update start` | Chercher une nouvelle version d'olscp / mettre à jour |
| `olscp settings key=value --apply` | Modifie un réglage |

## Applications Node.js, Python et Ruby

olscp lit les réglages Passenger que cPanel Application Manager écrit dans la configuration Apache et que les sélecteurs Node.js et Python de CloudLinux écrivent dans `.htaccess` : `PassengerAppRoot`, `PassengerBaseURI`, `PassengerAppType`, `PassengerStartupFile`, `PassengerNodejs`, `PassengerPython`, `PassengerRuby`, `PassengerAppEnv`, `PassengerAppLogFile` et `SetEnv`. Chaque application tourne sous l'utilisateur du compte, démarre à la première requête et continue de tourner lors des redémarrages du serveur.

Les clients continuent d'utiliser **cPanel > Application Manager** pour enregistrer leurs applications :

![Applications enregistrées dans cPanel Application Manager](../app-manager.png)

**cPanel > Application Status** affiche les applications du client, les redémarre et affiche leur journal :

![Application Status dans cPanel](../app-status.png)

![Journal d'une application dans cPanel](../app-log.png)

La page **Apps** du plugin WHM liste les applications de tous les comptes avec leur état, leur interpréteur, leur fichier journal et un bouton de redémarrage :

![Applications Node.js, Python et Ruby dans le plugin WHM](../apps.png)

- Les applications Node.js tournent via le lanceur Node.js d'OpenLiteSpeed. Les appels à `listen()` sont redirigés vers le socket qu'OpenLiteSpeed attribue à l'application.
- Les applications Python tournent via `libexec/lswsgi.py`, un petit serveur WSGI qui fonctionne avec n'importe quel interpréteur ou environnement virtuel Python 3.6 ou plus récent. Le fichier de démarrage doit définir `application` (par défaut `passenger_wsgi.py`).
- Les applications Ruby tournent via `libexec/lsrack.rb`, un petit serveur Rack pour Ruby 2.5 ou plus récent. Il charge `config.ru` avec Bundler quand l'application a un `Gemfile`, donc `bundle install` avec un chemin local fonctionne. La gem `rack` doit être installée pour l'application. `RACK_ENV` et `RAILS_ENV` suivent `PassengerAppEnv`.
- Pour redémarrer une application, faites un touch sur `tmp/restart.txt` à la racine de l'application, ou utilisez **cPanel > Application Status** ou **WHM > Plugins > OpenLiteSpeed > Apps**. Une modification des réglages la redémarre automatiquement.
- La sortie va dans `stderr.log` à la racine de l'application, ou dans `PassengerAppLogFile` quand ce fichier se trouve dans le répertoire personnel.
- Les sous-répertoires de la racine des documents situés sous l'URI de l'application sont servis comme fichiers statiques, comme avec Passenger. `/.well-known/` reste accessible pour AutoSSL.
- Le type d'application est déduit du fichier de démarrage (`passenger_wsgi.py`, `app.js` ou `config.ru`), sauf si `PassengerAppType` est défini. Un chemin d'interpréteur qui ne pointe pas vers Node.js, Python ou Ruby est remplacé par celui du système.
- La racine de l'application doit se trouver dans le répertoire personnel du compte. Quand la configuration Apache contient `PassengerDisableHtaccess on`, ce qui est le réglage par défaut de cPanel, les réglages Passenger de `.htaccess` sont ignorés.

## Version de PHP par répertoire

MultiPHP écrit la version de PHP d'un domaine dans `.htaccess` sous la forme `AddHandler application/x-httpd-ea-phpXX`. Quand un sous-répertoire utilise une autre version que son domaine, olscp associe les fichiers PHP de ce répertoire au processus LSAPI de cette version pour le compte, et la version s'applique comme avec Apache. Il faut pour cela le mode PHP LSAPI et le paquet LSAPI de cette version, tous deux sur la page **PHP** du plugin WHM.

## En-têtes de cache dans FilesMatch

Les plugins de cache comme WP Rocket et W3 Total Cache écrivent dans `.htaccess` des blocs `<FilesMatch>` qui ne définissent que des en-têtes ou des durées d'expiration pour certains types de fichiers. olscp transforme chaque bloc en un contexte regex qui conserve les règles d'accès, les réglages PHP et les règles de réécriture de son répertoire. Ainsi, une requête vers un `sitemap.xml` absent atteint toujours WordPress et les répertoires protégés restent protégés.

## CloudLinux

Sous CloudLinux, OpenLiteSpeed peut lancer PHP et les applications dans le LVE du compte et, si CageFS est installé, dans son CageFS. C'est désactivé par défaut ; le tableau de bord indique quand CloudLinux est détecté. Activez-le dans **Settings > CloudLinux** (Auto, LVE, LVE and CageFS) ou avec `olscp settings cloudlinux=auto --apply`. olscp ajoute ses propres fichiers à CageFS avec `/etc/cagefs/conf.d/olscp.cfg`, lance `cagefsctl --update` et redémarre les processus PHP et des applications. Les limites de ressources viennent alors de LVE Manager et les limites cgroups v2 d'olscp sont désactivées.

## Désinstallation

```bash
bash uninstall.sh          # switch back to Apache, remove the plugins and services
bash uninstall.sh --purge  # also delete /usr/local/olscp, settings, cache and logs
```

## Limites

- Non traduits depuis `.htaccess` : `<If>`, `Require host/expr`, `AuthType Digest`, et les blocs `<FilesMatch>` qui définissent plus que des en-têtes et des durées d'expiration.
- Les applications Ruby ne peuvent pas utiliser les WebSockets ni `rack.hijack`.
- La prise en charge de CloudLinux utilise les hooks LVE et CageFS intégrés à OpenLiteSpeed. Elle a été testée avec un substitut de `liblve`, pas encore sur un serveur CloudLinux sous licence.
- Le listage des répertoires n'est pas disponible pour les sites en PHP-FPM, car les pools FPM de cPanel restreignent `doc_root`. Il fonctionne avec LSAPI.
- Les clients sans SNI sur des IP dédiées reçoivent le certificat du serveur.
- Les archives des versions ne sont pas signées. Les mises à jour reposent sur la connexion HTTPS à GitHub ; les binaires précompilés sont en plus vérifiés avec le SHA-256 de `build/prebuilt.txt`.

## Contribuer

Les rapports de bugs et les pull requests sont les bienvenus, voir [CONTRIBUTING.md](../../CONTRIBUTING.md). Signalez les problèmes de sécurité en privé, comme décrit dans [SECURITY.md](../../SECURITY.md).

## Licence

GPL-3.0, voir [LICENSE](../../LICENSE). OpenLiteSpeed est développé par LiteSpeed Technologies et distribué sous licence GPL-3.0 ; le patch de `build/patches/` est distribué sous la même licence. Ce projet n'est ni affilié à LiteSpeed Technologies ou à cPanel, L.L.C., ni approuvé par eux. LiteSpeed, OpenLiteSpeed, LSCache, cPanel et WHM sont des marques de leurs propriétaires respectifs.

Du même auteur : [OpenLiteSpeed for Windows](https://github.com/NeuralFoundry/openlitespeed-windows), une version native d'OpenLiteSpeed pour Windows.
