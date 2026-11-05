[English](../../README.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | **Português** | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [한국어](README.ko.md) | [Bahasa Indonesia](README.id.md)

# OpenLiteSpeed for cPanel and WHM

Site: [openlitespeed.dev/cpanel-whm](https://openlitespeed.dev/cpanel-whm/)

**olscp** leva o OpenLiteSpeed para o cPanel: ele executa o [OpenLiteSpeed](https://openlitespeed.org) em servidores cPanel/WHM como substituto direto do Apache. Ele lê a configuração existente do Apache e os dados das contas do cPanel, gera a configuração do OpenLiteSpeed, mantém tudo sincronizado automaticamente e adiciona um plugin para o WHM e um plugin para o cPanel para gerenciar tudo. É gratuito e de código aberto sob a licença GPL-3.0.

![Painel do plugin do WHM do olscp](../dashboard.png)

## Recursos

- Funciona com o cPanel como ele é: contas, domínios adicionais, subdomínios e domínios estacionados, AutoSSL, suspensões, MultiPHP, `restartsrv_httpd`, chkservd e atualizações do EasyApache
- Troca segura: depois da troca, cada site é verificado por HTTP e HTTPS, e o servidor volta automaticamente para o Apache se algum site que funcionava no Apache falhar no OpenLiteSpeed. Um teste a seco (dry run) verifica antes cada site nas portas de pré-visualização, enquanto o Apache continua atendendo
- Lê o `httpd.conf` e todos os includes, então as configurações personalizadas do Apache e os virtual hosts extras são mantidos
- Suporte a `.htaccess`: regras de reescrita, Directory Privacy, Require/Allow/Deny, cabeçalhos, expires, redirecionamentos, páginas de erro, tipos MIME, bloqueio de bots com `SetEnvIf`, `php_value`, cabeçalhos de cache em `<FilesMatch>` (WP Rocket, W3 Total Cache) e uma versão de PHP diferente por diretório
- `.htaccess` ao vivo: alterações de reescrita são aplicadas em até um segundo sem reinício, com um binário com patch pré-compilado ou um compilado no servidor
- PHP pelos pools PHP-FPM do cPanel ou LSAPI por conta, em modo detached para que os reinícios mantenham o OPcache
- Aplicações Node.js, Python e Ruby do cPanel Application Manager e dos seletores do CloudLinux, iniciadas pelo OpenLiteSpeed com o usuário da conta
- CloudLinux LVE e CageFS para PHP e aplicações, quando ativado
- LSCache com armazenamento por site, gerenciamento de cache do WordPress e um plugin do cPanel para os usuários finais
- ModSecurity com os conjuntos de regras do cPanel/OWASP
- Proteção contra força bruta no WordPress, limite de requisições para bots e limites de recursos com cgroups v2 por usuário ou pacote
- HTTP/3 (QUIC) com uma lista de domínios para desativar, Brotli, IPv6, estatísticas em tempo real com taxa de acerto do cache e uso dos pools de aplicações, e um modo de pré-visualização nas portas 8080/8443
- Atualizações com um clique pelo plugin do WHM

## Requisitos

- cPanel & WHM 11.130 ou mais recente
- AlmaLinux, Rocky Linux ou CloudLinux 8 ou 9, x86_64
- Versões de PHP do EasyApache 4

## Instalação

```bash
git clone https://github.com/NeuralFoundry/openlitespeed-cpanel.git
cd openlitespeed-cpanel
bash install.sh
```

O instalador baixa o OpenLiteSpeed do repositório oficial da LiteSpeed, verifica o pacote com as chaves GPG fixadas em `keys/`, instala o `lsphp` para cada versão de PHP do EasyApache e registra o plugin do WHM. O Apache continua atendendo até você fazer a troca.

1. Teste a seco opcional: clique em **Dry run** no painel ou execute `olscp dry-run`. O OpenLiteSpeed inicia nas portas 8080/8443 e cada site é verificado enquanto o Apache continua atendendo; você vê quais sites, se houver algum, deixariam de funcionar.
2. Troca: abra **WHM > Plugins > OpenLiteSpeed** e clique em **Switch to OpenLiteSpeed**, ou execute `olscp enable`. Depois da troca, cada site é verificado e o servidor volta automaticamente para o Apache se algum site que funcionava no Apache falhar. Use `olscp enable --no-rollback` para manter o OpenLiteSpeed mesmo quando alguns sites falharem.
3. Para voltar ao Apache a qualquer momento: `olscp disable`.

Servidores que não conseguem acessar `rpms.litespeedtech.com` podem instalar a partir de um pacote local:

```bash
OLSCP_OLS_RPM=/root/openlitespeed-1.9.4-2.el9.x86_64.rpm bash install.sh
```

## .htaccess ao vivo

O binário padrão do OpenLiteSpeed carrega as regras de reescrita do `.htaccess` uma única vez. O olscp inclui um pequeno patch (`build/patches/`) que recarrega as regras de reescrita alteradas em até um segundo e detecta novos arquivos `.htaccess` na primeira requisição, sem reinício. As outras diretivas são aplicadas automaticamente com um reinício suave (graceful restart).

Cada release traz o binário com patch para EL8 e EL9. O olscp baixa o binário da release, confere o SHA-256 em `build/prebuilt.txt` e passa a usá-lo:

```bash
olscp ols fetch --use  # download the prebuilt binary and switch to it
olscp ols build        # or compile it on the server in the background, about 10 minutes
olscp ols use olscp    # switch to a compiled build, "olscp ols use official" switches back
```

A compilação instala as ferramentas de build com `dnf` e baixa o código-fonte do OpenLiteSpeed do GitHub em commits fixados. Para obter o binário pré-compilado durante a instalação, execute `OLSCP_FETCH_OLS=1 bash install.sh`. As mesmas ações estão na página **Version** do plugin do WHM.

![Configuração do Apache importada pelo olscp](../apache.png)

## Atualizações

A página **Version** do plugin do WHM mostra a release mais recente e atualiza o olscp com um clique. A atualização baixa a release do GitHub, executa o instalador dela e recarrega o OpenLiteSpeed de forma suave. Um binário pré-compilado que o olscp baixou antes é substituído pelo da nova release.

![Binário pré-compilado e atualizações no plugin do WHM](../version.png)

```bash
olscp update check     # look for a new release
olscp update start     # update in the background, log in /var/log/olscp-update.log
```

## Linha de comando

| Comando | Descrição |
|---|---|
| `olscp status` | Status do servidor, do watcher e da sincronização |
| `olscp enable` / `olscp disable` | Trocar para o OpenLiteSpeed / voltar ao Apache |
| `olscp restart` | Gera a configuração de novo e reinicia de forma suave |
| `olscp apache report` | Configurações lidas da configuração do Apache |
| `olscp htaccess report` | Diretivas do `.htaccess` que não puderam ser aplicadas |
| `olscp apps` / `olscp apps restart --vhost example.com --uri /` | Aplicações Node.js, Python e Ruby / reiniciar uma |
| `olscp cache list` / `olscp cache purge --all` | Sites com LSCache / limpar o cache |
| `olscp ols versions` / `olscp ols upgrade` | Versão do OpenLiteSpeed e atualização |
| `olscp ols fetch --use` | Baixa o binário pré-compilado com `.htaccess` ao vivo e passa a usá-lo |
| `olscp update check` / `olscp update start` | Procurar uma nova release do olscp / atualizar |
| `olscp settings key=value --apply` | Altera uma configuração |

## Aplicações Node.js, Python e Ruby

O olscp lê as configurações do Passenger que o cPanel Application Manager grava na configuração do Apache e que os seletores Node.js e Python do CloudLinux gravam no `.htaccess`: `PassengerAppRoot`, `PassengerBaseURI`, `PassengerAppType`, `PassengerStartupFile`, `PassengerNodejs`, `PassengerPython`, `PassengerRuby`, `PassengerAppEnv`, `PassengerAppLogFile` e `SetEnv`. Cada aplicação roda com o usuário da conta, é iniciada na primeira requisição e continua rodando quando o servidor reinicia.

Os clientes continuam usando o **cPanel > Application Manager** para registrar suas aplicações:

![Aplicações registradas no cPanel Application Manager](../app-manager.png)

O **cPanel > Application Status** mostra as aplicações do próprio cliente, reinicia essas aplicações e mostra o log delas:

![Application Status no cPanel](../app-status.png)

![Log de aplicação no cPanel](../app-log.png)

A página **Apps** do plugin do WHM lista as aplicações de todas as contas com o estado, o interpretador, o arquivo de log e um botão de reinício:

![Aplicações Node.js, Python e Ruby no plugin do WHM](../apps.png)

- Aplicações Node.js rodam pelo inicializador Node.js do OpenLiteSpeed. Chamadas a `listen()` são redirecionadas para o socket que o OpenLiteSpeed entrega à aplicação.
- Aplicações Python rodam por `libexec/lswsgi.py`, um pequeno servidor WSGI que funciona com qualquer interpretador ou ambiente virtual Python 3.6 ou mais recente. O arquivo de inicialização precisa definir `application` (padrão `passenger_wsgi.py`).
- Aplicações Ruby rodam por `libexec/lsrack.rb`, um pequeno servidor Rack para Ruby 2.5 ou mais recente. Ele carrega o `config.ru` com o Bundler quando a aplicação tem um `Gemfile`, então `bundle install` com um caminho local funciona. A gem `rack` precisa estar instalada para a aplicação. `RACK_ENV` e `RAILS_ENV` seguem `PassengerAppEnv`.
- Para reiniciar uma aplicação, use touch em `tmp/restart.txt` na raiz da aplicação, ou use **cPanel > Application Status** ou **WHM > Plugins > OpenLiteSpeed > Apps**. Configurações alteradas reiniciam a aplicação automaticamente.
- A saída vai para `stderr.log` na raiz da aplicação, ou para `PassengerAppLogFile` quando ele está dentro do diretório home.
- Subdiretórios da raiz de documentos sob a URI da aplicação são servidos como arquivos estáticos, como no Passenger. `/.well-known/` continua acessível para o AutoSSL.
- O tipo da aplicação vem do arquivo de inicialização (`passenger_wsgi.py`, `app.js` ou `config.ru`), a menos que `PassengerAppType` esteja definido. Um caminho de interpretador que não aponte para Node.js, Python ou Ruby é substituído pelo do sistema.
- A raiz da aplicação precisa estar dentro do diretório home da conta. Quando a configuração do Apache tem `PassengerDisableHtaccess on`, que é o padrão do cPanel, as configurações do Passenger no `.htaccess` são ignoradas.

## Versão de PHP por diretório

O MultiPHP grava a versão de PHP de um domínio como `AddHandler application/x-httpd-ea-phpXX` no `.htaccess`. Quando um subdiretório usa uma versão diferente da do seu domínio, o olscp mapeia os arquivos PHP desse diretório para o processo LSAPI dessa versão para a conta, então a versão vale como no Apache. Isso exige o modo PHP LSAPI e o pacote LSAPI dessa versão, os dois na página **PHP** do plugin do WHM.

## Cabeçalhos de cache em FilesMatch

Plugins de cache como WP Rocket e W3 Total Cache gravam no `.htaccess` blocos `<FilesMatch>` que só definem cabeçalhos ou tempos de expiração para alguns tipos de arquivo. O olscp transforma cada bloco em um contexto regex que mantém as regras de acesso, as configurações de PHP e as regras de reescrita do seu diretório, então uma requisição para um `sitemap.xml` inexistente ainda chega ao WordPress e os diretórios protegidos continuam protegidos.

## CloudLinux

No CloudLinux, o OpenLiteSpeed pode iniciar o PHP e as aplicações dentro do LVE da conta e, quando o CageFS está instalado, dentro do CageFS dela. Isso vem desativado por padrão; o painel mostra quando o CloudLinux é detectado. Ative em **Settings > CloudLinux** (Auto, LVE, LVE and CageFS) ou com `olscp settings cloudlinux=auto --apply`. O olscp adiciona os próprios arquivos ao CageFS com `/etc/cagefs/conf.d/olscp.cfg`, executa `cagefsctl --update` e reinicia os processos de PHP e das aplicações. A partir daí, os limites de recursos vêm do LVE Manager e os limites de cgroups v2 do olscp são desativados.

## Desinstalação

```bash
bash uninstall.sh          # switch back to Apache, remove the plugins and services
bash uninstall.sh --purge  # also delete /usr/local/olscp, settings, cache and logs
```

## Limitações

- Não são traduzidos do `.htaccess`: `<If>`, `Require host/expr`, `AuthType Digest` e blocos `<FilesMatch>` que definem mais do que cabeçalhos e tempos de expiração.
- Aplicações Ruby não podem usar WebSockets nem `rack.hijack`.
- O suporte ao CloudLinux usa os hooks de LVE e CageFS embutidos no OpenLiteSpeed. Ele foi testado com um substituto de `liblve`, ainda não em um servidor CloudLinux licenciado.
- A listagem de diretórios não está disponível para sites em PHP-FPM, porque os pools FPM do cPanel restringem `doc_root`. Ela funciona com LSAPI.
- Clientes sem SNI em IPs dedicados recebem o certificado do servidor.
- Os arquivos das releases não são assinados. As atualizações dependem da conexão HTTPS com o GitHub; os binários pré-compilados também são conferidos com o SHA-256 em `build/prebuilt.txt`.

## Como contribuir

Relatos de bugs e pull requests são bem-vindos, veja [CONTRIBUTING.md](../../CONTRIBUTING.md). Relate problemas de segurança de forma privada, como descrito em [SECURITY.md](../../SECURITY.md).

## Licença

GPL-3.0, veja [LICENSE](../../LICENSE). O OpenLiteSpeed é desenvolvido pela LiteSpeed Technologies e licenciado sob a GPL-3.0; o patch em `build/patches/` é distribuído sob a mesma licença. Este projeto não é afiliado nem endossado pela LiteSpeed Technologies ou pela cPanel, L.L.C. LiteSpeed, OpenLiteSpeed, LSCache, cPanel e WHM são marcas comerciais de seus respectivos proprietários.

Do mesmo autor: [OpenLiteSpeed for Windows](https://github.com/NeuralFoundry/openlitespeed-windows), uma build nativa do OpenLiteSpeed para Windows.
