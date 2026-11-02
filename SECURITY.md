# Security policy

olscp runs as root on web servers, so security reports are taken seriously.

## Supported versions

Security fixes are made for the latest version on the `main` branch.

## Reporting a vulnerability

Do not open a public issue. Report the problem privately through GitHub:
[Report a vulnerability](https://github.com/NeuralFoundry/openlitespeed-cpanel/security/advisories/new)

Please include the olscp version, the steps to reproduce and what an attacker can achieve. Reports are acknowledged within 7 days, and you will be credited in the advisory unless you prefer otherwise.

## Scope

In scope: the olscp code, including the WHM and cPanel plugins, the AdminBin scripts, the command line tools, the watcher, the generated OpenLiteSpeed configuration, the application servers in `libexec/`, the update and prebuilt binary downloads, and the patch in `build/patches/`.

Problems in OpenLiteSpeed itself should be reported to [LiteSpeed Technologies](https://openlitespeed.org), and problems in cPanel or WHM to [cPanel](https://cpanel.net/security/).
