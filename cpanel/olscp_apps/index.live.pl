#!/usr/local/cpanel/3rdparty/bin/perl

use strict;
use warnings;

use Cpanel::LiveAPI        ();
use Cpanel::AdminBin::Call ();
use Fcntl qw(O_RDONLY O_NOFOLLOW);

my %TYPES = ( node => 'Node.js', wsgi => 'Python', rack => 'Ruby' );
my $LOG_BYTES = 131072;
my $LOG_LINES = 300;

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

sub admin {
    my @args = @_;
    my $res  = eval { Cpanel::AdminBin::Call::call( 'Olscp', 'Apps', @args ) };
    if ( !$res ) {
        ( my $e = "$@" ) =~ s/\s+\z//;
        return { error => $e || 'the server did not answer' };
    }
    return $res;
}

sub read_log {
    my ($path) = @_;
    my $home = ( getpwuid($<) )[7] // '';
    $home =~ s{/+\z}{};
    return ( undef, 'Log file is outside the home directory' )
      unless length $home && defined $path && index( $path, "$home/" ) == 0 && $path !~ m{/\.\.(?:/|\z)};
    return ( '', '' ) unless -e $path;
    sysopen( my $fh, $path, O_RDONLY | O_NOFOLLOW ) or return ( undef, "Cannot open the log file: $!" );
    my $size = -s $fh;
    my $from = $size > $LOG_BYTES ? $size - $LOG_BYTES : 0;
    seek( $fh, $from, 0 );
    local $/;
    my $text = <$fh> // '';
    close $fh;
    $text =~ s/\A[^\n]*\n// if $from;
    my @lines = split /\n/, $text;
    @lines = @lines[ -$LOG_LINES .. -1 ] if @lines > $LOG_LINES;
    return ( join( "\n", @lines ), '' );
}

my $cpanel = Cpanel::LiveAPI->new();
my %form   = parse_form();
my ( $ok, $err );

if ( ( $ENV{'REQUEST_METHOD'} // '' ) eq 'POST' && ( $form{'action'} // '' ) eq 'restart' ) {
    my $r = admin( 'RESTART', $form{'vhost'} // '', $form{'uri'} // '' );
    if   ( $r->{'error'} ) { $err = $r->{'error'} }
    else                   { $ok  = 'Restarted ' . ( $form{'vhost'} // '' ) . ( $form{'uri'} // '' ) }
}

my $data   = admin('LIST');
my $apps   = ref $data->{'apps'} eq 'ARRAY'   ? $data->{'apps'}   : [];
my $issues = ref $data->{'issues'} eq 'ARRAY' ? $data->{'issues'} : [];
my $show   = defined $form{'log'} && $form{'log'} =~ /\A\d{1,4}\z/ && $form{'log'} < @$apps ? $apps->[ $form{'log'} ] : undef;

print "Content-type: text/html; charset=utf-8\r\n\r\n";
print $cpanel->header( 'Application Status', 'olscp_apps' );
print <<'CSS';
<style>
.ola{max-width:1100px}
.ola-wrap{overflow-x:auto;margin-top:6px;border:1px solid #dde3e7;border-radius:8px;background:#fff}
.ola-table{width:100%;border-collapse:collapse;background:#fff;margin:0}
.ola-table th{background:#f5f7f9;color:#56646d;font-size:12px;font-weight:700;text-align:left;padding:9px 12px;border-bottom:1px solid #dde3e7;white-space:nowrap}
.ola-table td{padding:10px 12px;border-top:1px solid #eef2f4;vertical-align:middle}
.ola-table tr:first-child td{border-top:0}
.ola-site{font-weight:700;word-break:break-all}
.ola-path{display:block;color:#6b7880;font-size:12px;word-break:break-all}
.ola-badge{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}
.ola-run{background:#e2f2e8;color:#17703f}.ola-idle{background:#edf1f3;color:#5f6d76}
.ola-act{display:flex;align-items:center;justify-content:flex-end;gap:6px;white-space:nowrap}
.ola-act form{margin:0}
.ola-empty{padding:28px 16px;text-align:center;color:#56646d;font-weight:600;background:#fff;border:1px solid #dde3e7;border-radius:8px}
.ola-h{font-size:15px;font-weight:700;margin:22px 0 6px}
.ola-log{margin:6px 0 0;padding:12px 14px;background:#13232c;color:#e7eff2;border-radius:8px;font:12px/1.5 SFMono-Regular,Consolas,monospace;white-space:pre-wrap;word-break:break-all;max-height:560px;overflow:auto}
.ola-bar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px}
</style>
CSS
print qq{<div class="ola">\n};
print '<div class="alert alert-success" role="status">' . esc($ok) . "</div>\n"        if $ok;
print '<div class="alert alert-danger" role="alert">Failed: ' . esc($err) . "</div>\n" if $err;
print '<div class="alert alert-danger" role="alert">' . esc( $data->{'error'} ) . "</div>\n" if $data->{'error'};

if ($show) {
    my ( $text, $lerr ) = read_log( $show->{'log'} );
    print '<div class="ola-bar"><div><span class="ola-site">' . esc( $show->{'vhost'} . $show->{'uri'} ) . '</span>';
    print '<span class="ola-path">' . esc( $show->{'log'} ) . '</span></div>';
    print '<div><a class="btn btn-default btn-sm" href="?log=' . esc( $form{'log'} ) . '">Reload</a> <a class="btn btn-default btn-sm" href="index.live.pl">Back</a></div></div>';
    if ($lerr) {
        print '<div class="alert alert-danger" role="alert">' . esc($lerr) . "</div>\n";
    }
    elsif ( !length $text ) {
        print qq{<div class="ola-empty" style="margin-top:8px">The log is empty</div>\n};
    }
    else {
        print '<pre class="ola-log">' . esc($text) . "</pre>\n";
    }
}
elsif ( !@$apps ) {
    print qq{<div class="ola-empty">No applications. <a href="../passenger/index.html">Application Manager</a></div>\n};
}
else {
    print qq{<div class="ola-wrap"><table class="ola-table"><thead><tr><th>Application</th><th>Type</th><th>Mode</th><th>State</th><th></th></tr></thead><tbody>\n};
    my $i = 0;
    for my $app (@$apps) {
        my $url = 'https://' . $app->{'vhost'} . $app->{'uri'};
        my $n   = int( $app->{'processes'} // 0 );
        print '<tr><td><a class="ola-site" href="' . esc($url) . '" target="_blank" rel="noopener">' . esc( $app->{'vhost'} . $app->{'uri'} ) . '</a>';
        print '<span class="ola-path">' . esc( $app->{'root'} ) . esc( $app->{'startup'} ) . '</span></td>';
        print '<td>' . esc( $TYPES{ $app->{'type'} } // $app->{'type'} ) . '<span class="ola-path">' . esc( $app->{'binary'} ) . '</span></td>';
        print '<td>' . esc( $app->{'mode'} ) . '</td>';
        print '<td>' . ( $n ? '<span class="ola-badge ola-run">Running</span>' : '<span class="ola-badge ola-idle">Idle</span>' ) . '</td>';
        print '<td><div class="ola-act">';
        print '<form method="post" data-c="Restart ' . esc( $app->{'vhost'} . $app->{'uri'} ) . '?" onsubmit="return confirm(this.dataset.c)"><input type="hidden" name="action" value="restart"><input type="hidden" name="vhost" value="' . esc( $app->{'vhost'} ) . '"><input type="hidden" name="uri" value="' . esc( $app->{'uri'} ) . '"><button class="btn btn-primary btn-sm">Restart</button></form>';
        print '<a class="btn btn-default btn-sm" href="?log=' . $i . '">Log</a>' if $app->{'log'};
        print "</div></td></tr>\n";
        $i++;
    }
    print "</tbody></table></div>\n";
}

if ( @$issues && !$show ) {
    print qq{<div class="ola-h">Not started</div><div class="ola-wrap"><table class="ola-table"><thead><tr><th>Domain</th><th>Reason</th></tr></thead><tbody>\n};
    print '<tr><td class="ola-site">' . esc( $_->{'vhost'} ) . '</td><td>' . esc( $_->{'issue'} ) . "</td></tr>\n" for @$issues;
    print "</tbody></table></div>\n";
}
print "</div>\n";

print $cpanel->footer();
$cpanel->end();
