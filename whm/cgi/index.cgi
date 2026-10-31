#!/usr/local/cpanel/3rdparty/bin/perl
#WHMADDON:olscp:OpenLiteSpeed
#ACLS:all

use strict;
use warnings;

use Cpanel::Form     ();
use Cpanel::JSON     ();
use Cpanel::Template ();
use Whostmgr::ACLS   ();

my $OLSCP   = '/usr/local/olscp/bin/olscp';
my $VERSION = '';
if ( open( my $vf, '<', '/usr/local/olscp/VERSION' ) ) {
    $VERSION = <$vf> // '';
    close $vf;
}
chomp $VERSION;

my %SETTINGS = (
    php_mode               => 'phpmode',
    lsphp_children         => 'int',
    lsphp_max_conns        => 'int',
    workers                => 'int',
    max_conns              => 'int',
    keepalive_timeout      => 'int',
    conn_timeout           => 'int',
    max_req_body           => 'size',
    mem_limit              => 'size',
    proc_soft_limit        => 'int',
    proc_hard_limit        => 'int',
    http2                  => 'bool',
    http3                  => 'bool',
    brotli                 => 'bool',
    cache_module           => 'bool',
    htaccess_watch         => 'bool',
    htaccess_scan_interval => 'int',
    webadmin_enabled       => 'bool',
    webadmin_listen        => 'listen',
    modsecurity            => 'onoff',
    ipv6                   => 'tristate',
    lscwp_version          => 'lscwpver',
    autoindex              => 'tristate',
    wp_protect             => 'wpmode',
    wp_protect_limit       => 'int',
    wp_protect_xmlrpc      => 'bool',
    protect_ban_minutes    => 'int',
    protect_whitelist      => 'iplist',
    bot_throttle           => 'int',
    bot_agents             => 'agents',
    block_bad_req          => 'bool',
    cgroups                => 'bool',
);

my %PAGES = map { $_ => 1 } qw(home sites stats cache quic htaccess apache security limits php version settings logs);
my %ALIAS = ( modsec => 'security', cpanel => 'cache' );

my %APACHE_TITLES = (
    aliases                => 'Aliases',
    denied_files           => 'Denied files',
    headers                => 'Headers',
    directory_index        => 'Directory index',
    timeouts               => 'Timeouts',
    proxies                => 'Proxies',
    trusted_proxies        => 'Trusted proxies',
    indexes                => 'Directory listing',
    keepalive              => 'Keep-alive',
    keepalive_timeout      => 'Keep-alive timeout',
    max_keepalive_requests => 'Max keep-alive requests',
    remoteip_header        => 'Client IP header',
    timeout                => 'Timeout',
    missing_includes       => 'Missing includes',
    version                => 'Apache version',
);
my %APACHE_BOOL = map { $_ => 1 } qw(indexes keepalive);
my %COL_TITLES = ( url => 'URL', uri => 'URI', cgi => 'CGI', ssl => 'SSL', docroot => 'Document root', ip => 'IP' );
my @APACHE_ORDER = qw(aliases proxies denied_files directory_index headers trusted_proxies);
my @COL_ORDER    = qw(name url uri path pattern regex target kind type value cgi file line directive docroot user ssl);

sub olscp {
    my @args = @_;
    my $pid  = open( my $fh, '-|' );
    return { error => "fork: $!" } unless defined $pid;
    if ( !$pid ) {
        open( STDERR, '>&', \*STDOUT );
        exec( $OLSCP, '--json', @args ) or exit 127;
    }
    local $/;
    my $out = <$fh>;
    close $fh;
    my $data = eval { Cpanel::JSON::Load($out) };
    return $data if ref $data;
    my @lines = grep { /\S/ } split /\n/, ( $out // '' );
    my $msg   = @lines ? $lines[-1] : 'no output from olscp';
    $msg = substr( $msg, 0, 300 ) . '...' if length $msg > 300;
    return { error => $msg };
}

sub valid_setting {
    my ( $type, $v ) = @_;
    return 0 unless defined $v;
    return $v =~ /^(?:auto|fpm|lsapi)$/                     if $type eq 'phpmode';
    return $v =~ /^(?:auto|off)$/                           if $type eq 'onoff';
    return $v =~ /^(?:auto|on|off)$/                        if $type eq 'tristate';
    return $v =~ /^(?:latest|\d+(?:\.\d+){1,3})$/           if $type eq 'lscwpver';
    return $v =~ /^(?:off|block)$/                          if $type eq 'wpmode';
    return $v =~ /^[0-9a-fA-F:.\/, ]{0,2000}$/              if $type eq 'iplist';
    return $v =~ /^[A-Za-z0-9 ._|-]{0,1000}$/               if $type eq 'agents';
    return $v =~ /^\d{1,7}$/                                if $type eq 'int';
    return $v =~ /^\d{1,5}[KMG]?$/                          if $type eq 'size';
    return $v =~ /^(?:0|1)$/                                if $type eq 'bool';
    return $v =~ /^(?:\d{1,3}(?:\.\d{1,3}){3}|\*):\d{2,5}$/ if $type eq 'listen';
    return 0;
}

sub selected_paths {
    my ($form) = @_;
    return grep { defined && m{\A/} } map { $form->{$_} } sort grep { /^path_\d+$/ } keys %$form;
}

sub duration {
    my ($s) = @_;
    return '' unless defined $s && $s =~ /^\d+$/;
    my $d = int( $s / 86400 );
    my $h = int( ( $s % 86400 ) / 3600 );
    my $m = int( ( $s % 3600 ) / 60 );
    return "${d}d ${h}h" if $d;
    return "${h}h ${m}m" if $h;
    return "${m}m"       if $m;
    return "${s}s";
}

sub is_bool {
    my ($x) = @_;
    return ref($x) && ref($x) !~ /^(?:HASH|ARRAY|CODE|SCALAR)$/;
}

sub flat {
    my ($x) = @_;
    return '' unless defined $x;
    return $x ? 'Yes' : 'No' if is_bool($x);
    return join( ' ', map { flat($_) } @$x ) if ref $x eq 'ARRAY';
    return join( ', ', map { "$_: " . flat( $x->{$_} ) } sort keys %$x ) if ref $x eq 'HASH';
    return "$x";
}

sub title_of {
    my ( $k, $map ) = @_;
    return $map->{$k} // ucfirst( join ' ', split /_/, $k );
}

sub table_of {
    my ($list) = @_;
    return { kind => 'none' } unless ref $list eq 'ARRAY' && @$list;
    if ( grep { ref $_ eq 'HASH' } @$list ) {
        my %k;
        for my $r (@$list) { $k{$_}++ for ref $r eq 'HASH' ? keys %$r : () }
        my @pref = grep { $k{$_} } @COL_ORDER;
        my %p    = map  { $_ => 1 } @pref;
        my @cols = ( @pref, sort grep { !$p{$_} } keys %k );
        my @rows = map {
            my $r = $_;
            [ map { ref $r eq 'HASH' ? flat( $r->{$_} ) : ( $_ eq $cols[0] ? flat($r) : '' ) } @cols ]
        } @$list;
        return { kind => 'table', cols => [ map { title_of( $_, \%COL_TITLES ) } @cols ], rows => \@rows };
    }
    if ( grep { ref $_ eq 'ARRAY' } @$list ) {
        my $n = 0;
        for (@$list) { $n = @$_ if ref $_ eq 'ARRAY' && @$_ > $n }
        return { kind => 'table', cols => [ map { '' } 1 .. $n ], rows => [ map { ref $_ eq 'ARRAY' ? [ map { flat($_) } @$_ ] : [ flat($_) ] } @$list ] };
    }
    return { kind => 'chips', chips => [ map { flat($_) } @$list ] };
}

sub apache_view {
    my ($r) = @_;
    return { error => 'no data' } unless ref $r eq 'HASH';
    return { error => $r->{'error'} } if $r->{'error'};
    my $g = ref $r->{'global'} eq 'HASH' ? $r->{'global'} : {};
    my ( %seen, @settings, @tables, @chips );
    push @settings, [ 'Apache version', $r->{'version'} ] if defined $r->{'version'} && !ref $r->{'version'};
    for my $k ( ( grep { exists $g->{$_} } @APACHE_ORDER ), sort keys %$g ) {
        next if $seen{$k}++;
        my $v     = $g->{$k};
        my $title = title_of( $k, \%APACHE_TITLES );
        if ( is_bool($v) || ( $APACHE_BOOL{$k} && defined $v && !ref $v ) ) {
            push @settings, [ $title, $v ? 'On' : 'Off' ];
        }
        elsif ( ref $v eq 'HASH' ) {
            push @settings, [ title_of( $_, \%APACHE_TITLES ), flat( $v->{$_} ) ] for sort keys %$v;
        }
        elsif ( ref $v eq 'ARRAY' ) {
            my $t = table_of($v);
            if    ( $t->{'kind'} eq 'none' )  { push @settings, [ $title, 'None' ] }
            elsif ( $t->{'kind'} eq 'chips' ) { push @chips,  { title => $title, %$t } }
            else                              { push @tables, { title => $title, %$t } }
        }
        else {
            push @settings, [ $title, defined $v && length $v ? "$v" : 'None' ];
        }
    }
    my $missing = table_of( $r->{'missing_includes'} );
    return {
        settings     => \@settings,
        tables       => \@tables,
        chips        => \@chips,
        missing      => $missing->{'kind'} eq 'none' ? [] : ( $missing->{'chips'} || [ map { join ' ', @$_ } @{ $missing->{'rows'} } ] ),
        extra_vhosts => table_of( $r->{'extra_vhosts'} ),
        unsupported  => table_of( $r->{'unsupported'} ),
        n_extra      => ref $r->{'extra_vhosts'} eq 'ARRAY' ? scalar @{ $r->{'extra_vhosts'} } : 0,
        n_unsup      => ref $r->{'unsupported'} eq 'ARRAY' ? scalar @{ $r->{'unsupported'} } : 0,
        parsed_files => $r->{'parsed_files'} // '',
        modules      => ref $r->{'modules'} eq 'ARRAY' ? [ map { flat($_) } @{ $r->{'modules'} } ] : [],
    };
}

Whostmgr::ACLS::init_acls();
print "Content-type: text/html; charset=utf-8\r\n\r\n";
if ( !Whostmgr::ACLS::hasroot() ) {
    print "<h1>Permission denied</h1>\n";
    exit;
}

my %FORM   = Cpanel::Form::parseform();
my $method = $ENV{'REQUEST_METHOD'} || 'GET';
my $action = $FORM{'action'} || '';
my $page   = $FORM{'page'}   || 'home';
$page = $ALIAS{$page} if $ALIAS{$page};
$page = 'home' unless $PAGES{$page};
my %result;

if ( $method eq 'POST' && $action ) {
    my $res;
    my %simple = (
        enable             => ['enable'],
        disable            => ['disable'],
        restart            => ['restart'],
        sync               => [ 'sync', '--restart' ],
        preview_start      => [ 'preview', 'start' ],
        preview_stop       => [ 'preview', 'stop' ],
        htaccess_scan      => [ 'htaccess', 'scan' ],
        cache_scan         => [ 'cache', 'scan' ],
        cache_scan_new     => [ 'cache', 'scan-new' ],
        cache_refresh      => [ 'cache', 'start', 'refresh' ],
        cache_mass_enable  => [ 'cache', 'start', 'mass-enable' ],
        cache_mass_disable => [ 'cache', 'start', 'mass-disable' ],
        cache_purge_all    => [ 'cache', 'purge', '--all' ],
        cpplugin_install   => [ 'cpanel-plugin', 'install' ],
        cpplugin_uninstall => [ 'cpanel-plugin', 'uninstall' ],
        ols_build          => [ 'ols', 'build' ],
    );
    if ( $simple{$action} ) {
        $res = olscp( @{ $simple{$action} } );
    }
    elsif ( $action eq 'webadmin_reset' ) {
        $res = olscp( 'webadmin', '--reset-password' );
        $result{'password'} = $res->{'password'} if ref $res eq 'HASH';
    }
    elsif ( $action eq 'ols_use' ) {
        my $target = $FORM{'target'} // '';
        $res = $target =~ /^(?:olscp|official)$/ ? olscp( 'ols', 'use', $target ) : { error => 'bad target' };
    }
    elsif ( $action eq 'cache_selected' ) {
        my $op    = $FORM{'op'} || '';
        my @paths = selected_paths( \%FORM );
        if ( !@paths ) {
            $res = { error => 'no site selected' };
        }
        elsif ( $op =~ /^(?:enable|disable|refresh)$/ ) {
            $res = olscp( 'cache', 'start', $op, map { ( '--path', $_ ) } @paths );
        }
        elsif ( $op =~ /^(?:flag|unflag)$/ ) {
            $res = olscp( 'cache', $op, map { ( '--path', $_ ) } @paths );
        }
        elsif ( $op eq 'purge' ) {
            my $list = olscp( 'cache', 'list' );
            my %vh   = map { $_->{'path'} => $_->{'vhost'} } @{ ref $list eq 'HASH' && $list->{'sites'} ? $list->{'sites'} : [] };
            my %uniq = map { $_ => 1 } grep { defined } map { $vh{$_} } @paths;
            $res = %uniq ? olscp( 'cache', 'purge', map { ( '--vhost', $_ ) } sort keys %uniq ) : { error => 'no matching domain' };
        }
        else { $res = { error => 'unknown operation' } }
    }
    elsif ( $action eq 'limits_set' ) {
        my $scope = $FORM{'scope'} // '';
        my $name  = $FORM{'name'}  // '';
        if ( $scope !~ /^(?:default|package|user)$/ || ( $scope ne 'default' && $name !~ /^[A-Za-z0-9_.\-]{1,64}$/ ) ) {
            $res = { error => 'bad scope' };
        }
        else {
            my @args = ( 'limits', 'set', '--scope', $scope );
            push @args, '--name', $name if $scope ne 'default';
            for my $k (qw(cpu mem tasks io)) {
                my $v = $FORM{$k} // '';
                if ( $v ne '' && $v !~ /^\d{1,7}$/ ) { $res = { error => "invalid $k" }; last }
                push @args, "--$k", $v if $v ne '';
            }
            $res ||= olscp(@args);
        }
    }
    elsif ( $action eq 'php_install' ) {
        my $n = $FORM{'name'} // '';
        $res = $n =~ /^ea-php\d{2}$/ ? olscp( 'php', 'install', $n ) : { error => 'bad version' };
    }
    elsif ( $action eq 'unblock' ) {
        my $ip = $FORM{'ip'} // '';
        $res = $ip =~ /^[0-9a-fA-F:.]{3,45}$/ ? olscp( 'blocked', 'unblock', $ip ) : { error => 'bad ip' };
    }
    elsif ( $action eq 'unblock_all' ) {
        $res = olscp( 'blocked', 'clear' );
    }
    elsif ( $action eq 'cache_force_version' ) {
        $res = olscp( 'cache', 'start', 'force-version' );
    }
    elsif ( $action eq 'quic_refresh' ) {
        $res = olscp( 'cache', 'quic', '--all' );
    }
    elsif ( $action eq 'ols_upgrade' ) {
        my $v = $FORM{'version'} // '';
        $res = $v =~ /^\d+\.\d+\.\d+$/ ? olscp( 'ols', 'upgrade', '--version', $v ) : { error => 'bad version' };
    }
    elsif ( $action eq 'settings' ) {
        my @pairs;
        my @keys = $FORM{'only'} ? grep { exists $SETTINGS{$_} } split /,/, $FORM{'only'} : ();
        $res = { error => 'no settings' } unless @keys;
        for my $k (@keys) {
            my $type = $SETTINGS{$k};
            my $v    = $type eq 'bool' ? ( $FORM{$k} ? 1 : 0 ) : $FORM{$k};
            next unless defined $v && ( length $v || $type eq 'iplist' || $type eq 'agents' );
            if ( !valid_setting( $type, $v ) ) {
                $res = { error => "invalid value: $k" };
                last;
            }
            push @pairs, "$k=$v";
        }
        $res ||= olscp( 'settings', @pairs, '--apply' );
    }
    else { $res = { error => 'unknown action' } }

    my $err = '';
    if ( ref $res eq 'HASH' ) {
        $err = $res->{'error'} // '';
        $err ||= 'operation reported failure' if exists $res->{'ok'} && !$res->{'ok'};
    }
    $result{'ok'}     = $err ? 0 : 1;
    $result{'error'}  = $err;
    $result{'steps'}  = ref $res eq 'ARRAY' ? [ map { flat($_) } @$res ] : [];
    $result{'action'} = $action;
}

my $status = olscp('status');
$status = {} unless ref $status eq 'HASH';
my $now     = time();
my $started = ref $status->{'ols'} eq 'HASH' ? $status->{'ols'}{'started'} : undef;

my %data = (
    page     => $page,
    version  => $VERSION,
    result   => \%result,
    status   => $status,
    settings => olscp('settings'),
    now      => $now,
    uptime   => ( $started && $started =~ /^\d+$/ && $started <= $now ) ? duration( $now - $started ) : '',
);

if ( $page eq 'home' ) {
    $data{'preview'} = olscp( 'preview', 'status' );
    $data{'cache'}   = olscp( 'cache', 'list' );
    $data{'modsec'}  = olscp('modsec');
    $data{'ht'}      = olscp( 'htaccess', 'report' );
    $data{'cpp'}     = olscp( 'cpanel-plugin', 'status' );
    $data{'stats'}   = olscp('stats');
    $data{'limits'}  = olscp( 'limits', 'show' );
}
elsif ( $page eq 'stats' ) {
    $data{'stats'}   = olscp('stats');
    $data{'refresh'} = 5;
}
elsif ( $page eq 'sites' ) {
    $data{'sites'} = olscp('vhosts');
}
elsif ( $page eq 'cache' ) {
    $data{'cache'} = olscp( 'cache', 'list' );
    $data{'cpp'}   = olscp( 'cpanel-plugin', 'status' );
    my $job = ref $data{'cache'} eq 'HASH' ? $data{'cache'}{'job'} : undef;
    $data{'refresh'} = 4 if ref $job eq 'HASH' && $job->{'running'};
}
elsif ( $page eq 'quic' ) {
    $data{'quic'} = olscp( 'cache', 'quic' );
}
elsif ( $page eq 'htaccess' ) {
    $data{'ht'} = olscp( 'htaccess', 'report' );
}
elsif ( $page eq 'apache' ) {
    $data{'apache'} = apache_view( olscp( 'apache', 'report' ) );
}
elsif ( $page eq 'security' ) {
    $data{'modsec'}  = olscp('modsec');
    $data{'ht'}      = olscp( 'htaccess', 'report' );
    $data{'blocked'} = olscp( 'blocked', 'list' );
}
elsif ( $page eq 'limits' ) {
    $data{'limits'} = olscp( 'limits', 'show' );
}
elsif ( $page eq 'php' ) {
    $data{'php'} = olscp( 'php', 'list' );
}
elsif ( $page eq 'version' ) {
    my $ver = olscp( 'ols', 'versions' );
    $data{'ver'} = $ver;
    my $job = ref $ver eq 'HASH' && ref $ver->{'build'} eq 'HASH' ? $ver->{'build'}{'job'} : undef;
    if ( ref $job eq 'HASH' ) {
        $data{'refresh'}   = 10 if $job->{'running'};
        $data{'build_age'} = duration( $now - $job->{'started'} ) if $job->{'running'} && $job->{'started'} && $job->{'started'} =~ /^\d+$/;
    }
}
elsif ( $page eq 'logs' ) {
    $data{'logs'} = olscp( 'logs', '--lines', '150' );
}

Cpanel::Template::process_template(
    'whostmgr',
    {
        'template_file' => 'olscp/index.tmpl',
        'data'          => \%data,
    },
);
