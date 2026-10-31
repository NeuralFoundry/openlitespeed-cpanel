#!/usr/local/cpanel/3rdparty/bin/perl

use strict;
use warnings;

use Cpanel::LiveAPI        ();
use Cpanel::JSON           ();
use Cpanel::AdminBin::Call ();

my %STATE = (
    enabled  => [ 'Enabled',       'olc-on' ],
    disabled => [ 'Disabled',      'olc-off' ],
    missing  => [ 'Not installed', 'olc-miss' ],
);

sub esc {
    my $s = shift // '';
    $s =~ s/&/&amp;/g;
    $s =~ s/</&lt;/g;
    $s =~ s/>/&gt;/g;
    $s =~ s/"/&quot;/g;
    return $s;
}

sub parse_form {
    my %f;
    my $q = $ENV{'QUERY_STRING'} // '';
    if ( ( $ENV{'REQUEST_METHOD'} // '' ) eq 'POST' ) {
        my $len = int( $ENV{'CONTENT_LENGTH'} // 0 );
        $len = 65536 if $len > 65536;
        my $body = '';
        read( STDIN, $body, $len ) if $len > 0;
        $q = join '&', grep { length } $q, $body;
    }
    for my $pair ( split /&/, $q ) {
        my ( $k, $v ) = split /=/, $pair, 2;
        next unless defined $k;
        for ( $k, $v ) {
            next unless defined;
            tr/+/ /;
            s/%([0-9A-Fa-f]{2})/chr(hex($1))/ge;
        }
        $f{$k} = $v;
    }
    return %f;
}

sub run_user {
    my @args = @_;
    my $pid  = open( my $fh, '-|' );
    return { error => "fork: $!" } unless defined $pid;
    if ( !$pid ) {
        open( STDERR, '>', '/dev/null' );
        exec( '/usr/local/olscp/bin/olscp-user', @args ) or exit 127;
    }
    local $/;
    my $out = <$fh>;
    close $fh;
    my $data = eval { Cpanel::JSON::Load($out) };
    return ref $data ? $data : { error => 'unexpected output from olscp-user' };
}

my $cpanel = Cpanel::LiveAPI->new();
my %form   = parse_form();
my ( $ok, $err );

if ( ( $ENV{'REQUEST_METHOD'} // '' ) eq 'POST' ) {
    my $a = $form{'action'} // '';
    if ( ( $a eq 'enable' || $a eq 'disable' ) && defined $form{'path'} && $form{'path'} =~ m{\A/} ) {
        my $r = run_user( $a, $form{'path'} );
        if ( $r->{'ok'} ) {
            $ok = $a eq 'enable' ? 'LSCache enabled' : 'LSCache disabled';
        }
        else {
            $err = $r->{'error'} // ( ref $r->{'site'} eq 'HASH' ? $r->{'site'}{'error'} : '' );
            $err ||= 'the plugin reported an error';
        }
    }
    elsif ( $a eq 'purge' && defined $form{'vhost'} && length $form{'vhost'} ) {
        if ( eval { Cpanel::AdminBin::Call::call( 'Olscp', 'Cache', 'PURGE', $form{'vhost'} ); 1 } ) {
            $ok = 'Cache purged for ' . $form{'vhost'};
        }
        else {
            ( $err = "$@" ) =~ s/\s+\z//;
            $err ||= 'purge failed';
        }
    }
}

my $data  = run_user('list');
my $sites = ref $data->{'sites'} eq 'ARRAY' ? $data->{'sites'} : [];

print "Content-type: text/html; charset=utf-8\r\n\r\n";
print $cpanel->header( 'LiteSpeed Cache', 'olscp_cache' );
print <<'CSS';
<style>
.olc{max-width:1100px}
.olc-table{width:100%;border-collapse:collapse;background:#fff;margin:0}
.olc-wrap{overflow-x:auto;margin-top:6px;border:1px solid #dde3e7;border-radius:8px;background:#fff}
.olc-table th{background:#f5f7f9;color:#56646d;font-size:12px;font-weight:700;text-align:left;padding:9px 12px;border-bottom:1px solid #dde3e7;white-space:nowrap}
.olc-table td{padding:10px 12px;border-top:1px solid #eef2f4;vertical-align:middle}
.olc-table tr:first-child td{border-top:0}
.olc-site{font-weight:700;word-break:break-all}
.olc-path{display:block;color:#6b7880;font-size:12px;word-break:break-all}
.olc-badge{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}
.olc-on{background:#e2f2e8;color:#17703f}.olc-off{background:#edf1f3;color:#5f6d76}.olc-miss{background:#fcf0d4;color:#875a00}.olc-err{background:#fde7e5;color:#b42318}
.olc-actions{white-space:nowrap;text-align:right}
.olc-actions form{display:inline-block;margin:0 0 0 6px}
.olc-empty{padding:28px 16px;text-align:center;color:#56646d;font-weight:600;background:#fff;border:1px solid #dde3e7;border-radius:8px}
</style>
CSS
print qq{<div class="olc">\n};
print '<div class="alert alert-success" role="status">' . esc($ok) . "</div>\n"           if $ok;
print '<div class="alert alert-danger" role="alert">Failed: ' . esc($err) . "</div>\n"    if $err;
print '<div class="alert alert-danger" role="alert">' . esc( $data->{'error'} ) . "</div>\n" if $data->{'error'};

if ( !@$sites ) {
    print qq{<div class="olc-empty">No WordPress sites found</div>\n};
}
else {
    print qq{<div class="olc-wrap"><table class="olc-table"><thead><tr><th>Site</th><th>WordPress</th><th>LSCache</th><th>Plugin</th><th></th></tr></thead><tbody>\n};
    for my $s (@$sites) {
        my $st = $s->{'lscache'} // 'error';
        my ( $label, $cls ) = @{ $STATE{$st} || [ 'Error', 'olc-err' ] };
        my $p   = esc( $s->{'path'} );
        my $act = $st eq 'enabled' ? 'disable' : 'enable';
        print '<tr><td><span class="olc-site">' . esc( $s->{'url'} ) . '</span><span class="olc-path">' . $p . '</span>';
        print '<span class="olc-path" style="color:#b42318">' . esc( $s->{'error'} ) . '</span>' if $s->{'error'};
        print '</td><td>' . esc( $s->{'wp_version'} ) . '</td>';
        print '<td><span class="olc-badge ' . $cls . '">' . esc($label) . '</span></td>';
        print '<td>' . esc( $s->{'plugin_version'} ) . '</td><td class="olc-actions">';
        if ( $st ne 'error' ) {
            print '<form method="post"><input type="hidden" name="action" value="' . $act . '"><input type="hidden" name="path" value="' . $p . '"><button class="btn btn-' . ( $act eq 'enable' ? 'primary' : 'default' ) . ' btn-sm">' . ( $act eq 'enable' ? 'Enable' : 'Disable' ) . '</button></form>';
        }
        print '<form method="post" data-c="Purge the cache of ' . esc( $s->{'vhost'} ) . '?" onsubmit="return confirm(this.dataset.c)"><input type="hidden" name="action" value="purge"><input type="hidden" name="vhost" value="' . esc( $s->{'vhost'} ) . '"><button class="btn btn-default btn-sm">Purge cache</button></form>';
        print "</td></tr>\n";
    }
    print "</tbody></table></div>\n";
}
print "</div>\n";

print $cpanel->footer();
$cpanel->end();
