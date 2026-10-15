#!/bin/bash
set -uo pipefail
echo "--- ip ---"
ip -4 addr || true
echo "--- listeners ---"
ss -ltn | awk 'NR==1 || /:443|:80 /' || true
echo "--- access ---"
tail -40 /var/log/nginx/access.log || true
echo "--- error ---"
tail -30 /var/log/nginx/error.log || true
echo "--- pub ---"
curl -skS -m 8 -o /dev/null -w "pub443 %{http_code}\n" --resolve delau.tech:443:81.177.141.93 https://delau.tech/auth/login/ || true
