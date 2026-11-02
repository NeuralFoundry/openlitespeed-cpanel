<?php
$in = fopen('php://stdin', 'r');
$raw = rtrim((string) fgets($in, 4096), "\r\n");
echo password_hash($raw, PASSWORD_BCRYPT), "\n";
