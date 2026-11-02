import os

BASE = '/usr/local/olscp'
OLS_ROOT = BASE + '/ws'
OLS_BIN_DIR = OLS_ROOT + '/bin'
OLS_CONF = OLS_ROOT + '/conf/httpd_config.conf'
OLS_VHOST_DIR = OLS_ROOT + '/conf/vhosts/olscp'
OLS_VERSION_FILE = OLS_ROOT + '/VERSION'
OLS_ADMIN_CONF = OLS_ROOT + '/admin/conf/admin_config.conf'

ETC = '/etc/olscp'
SETTINGS = ETC + '/settings.json'
ACTIVE_FLAG = ETC + '/active'
STATE = '/var/lib/olscp'
BACKUP = STATE + '/backup'
RUN = '/run/olscp'
LOG = '/var/log/olscp.log'
SYNC_LOCK = RUN + '/sync.lock'
HT_NOTIFY = RUN + '/ht.sock'
STATUS_FILE = STATE + '/status.json'
PAGES = BASE + '/pages'

APACHE_PID = '/run/apache2/httpd.pid'
APACHE_ERROR_LOG = '/etc/apache2/logs/error_log'
APACHE_ACCESS_LOG = '/etc/apache2/logs/access_log'
APACHE_CONF = '/etc/apache2/conf/httpd.conf'
DOMLOGS = '/etc/apache2/logs/domlogs'
HTTPD = '/usr/sbin/httpd'
HTTPD_REAL = '/usr/sbin/httpd.olscp-apache'
WRAPPER_SRC = BASE + '/libexec/httpd'

USERDATA = '/var/cpanel/userdata'
CPANEL_USERS = '/var/cpanel/users'
SUSPENDED = '/var/cpanel/suspended'
CPANEL_CONFIG = '/var/cpanel/cpanel.config'
SSL_DIR = '/var/cpanel/ssl/apache_tls'
SERVICE_SSL = '/var/cpanel/ssl/cpanel/mycpanel.pem'
EA4_PHP_CONF = '/etc/cpanel/ea4/php.conf'
EA_PHP_ROOT = '/opt/cpanel'
WWWACCT = '/etc/wwwacct.conf'
MAINIP = '/var/cpanel/mainip'
CLOUDFLARE_CONF = '/etc/apache2/conf.d/includes/cloudflare.conf'
CGI_SYS = '/usr/local/cpanel/cgi-sys'
DEFAULT_DOCROOT = '/var/www/html'
CACHE_ROOT = '/home/olscp-cache'
WP_CLI = BASE + '/bin/wp-cli.phar'
MODSEC_AUDIT = '/etc/apache2/logs/modsec_audit.log'

SERVICE_PORTS = {
    'cpanel': 2082,
    'webmail': 2095,
    'whm': 2086,
    'webdisk': 2077,
    'cpcalendars': 2079,
    'cpcontacts': 2079,
}
ACTIVESYNC_PORT = 2090

INDEX_FILES = [
    'index.php', 'index.php8', 'index.php7', 'index.php5', 'index.perl', 'index.pl', 'index.plx',
    'index.ppl', 'index.cgi', 'index.jsp', 'index.jp', 'index.phtml', 'index.shtml', 'index.xhtml',
    'index.html', 'index.htm', 'index.js',
]
PHP_SUFFIXES = ['php', 'php8', 'php7', 'php5', 'phtml']

DEFAULT_SETTINGS = {
    'workers': 0,
    'php_mode': 'auto',
    'lsphp_children': 10,
    'lsphp_max_conns': 10,
    'mem_limit': '2047M',
    'proc_soft_limit': 400,
    'proc_hard_limit': 500,
    'http2': True,
    'http3': False,
    'brotli': True,
    'webadmin_listen': '127.0.0.1:7080',
    'webadmin_enabled': False,
    'cache_root': CACHE_ROOT,
    'modsecurity': 'auto',
    'ipv6': 'auto',
    'internal_port': 49280,
    'htaccess_scan_interval': 900,
    'lscwp_version': 'latest',
    'autoindex': 'auto',
    'wp_protect': 'off',
    'wp_protect_limit': 20,
    'wp_protect_xmlrpc': True,
    'protect_ban_minutes': 15,
    'protect_whitelist': '',
    'bot_throttle': 0,
    'bot_agents': 'GPTBot|ClaudeBot|anthropic-ai|CCBot|Bytespider|Amazonbot|PerplexityBot|meta-externalagent|Google-Extended|Applebot-Extended|ImagesiftBot|PetalBot|DataForSeoBot|AhrefsBot|SemrushBot|MJ12bot|DotBot|BLEXBot',
    'block_bad_req': True,
    'cgroups': False,
    'cloudlinux': 'off',
    'htaccess_watch': True,
    'cache_module': True,
    'max_conns': 10000,
    'keepalive_timeout': 5,
    'conn_timeout': 300,
    'max_req_body': '2047M',
}


SETTING_CHOICES = {'cloudlinux': ('auto', 'off', 'lve', 'cagefs')}


def ensure_dirs():
    for d in (ETC, STATE, BACKUP, RUN, OLS_VHOST_DIR):
        os.makedirs(d, exist_ok=True)
