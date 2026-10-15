#!/bin/bash
# Включить listen 443, если сертификат ещё лежит на сервере. HTTP :80 не выключаем.
set -uo pipefail

echo "--- nginx procs ---"
ps -eo lstart,cmd | grep nginx | grep -v grep || true
echo "--- certs ---"
find /etc/letsencrypt -name 'fullchain.pem' 2>/dev/null || true

CERT=/etc/letsencrypt/live/delau.tech/fullchain.pem
KEY=/etc/letsencrypt/live/delau.tech/privkey.pem
if [[ ! -f "$CERT" || ! -f "$KEY" ]]; then
  echo "NO CERTS"
  exit 0
fi

cp /etc/nginx/sites-available/delayu /etc/nginx/sites-available/delayu.bak-http
cat > /etc/nginx/sites-available/delayu << 'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name delau.tech novorossiysk.delau.tech;
    client_max_body_size 50M;
    location /static/ { alias /opt/delayu/staticfiles/; expires 7d; }
    location /media/ { alias /opt/delayu/media/; expires 1d; }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name delau.tech novorossiysk.delau.tech;
    ssl_certificate /etc/letsencrypt/live/delau.tech/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/delau.tech/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    client_max_body_size 50M;
    location /static/ { alias /opt/delayu/staticfiles/; expires 7d; }
    location /media/ { alias /opt/delayu/media/; expires 1d; }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }
}
NGINX

if nginx -t; then
  systemctl reload nginx
  echo "reloaded"
else
  cp /etc/nginx/sites-available/delayu.bak-http /etc/nginx/sites-available/delayu
  echo "nginx -t failed, config restored"
  nginx -t || true
fi
ss -ltn | awk 'NR==1 || /:443|:80 /' || true
curl -skS -m 8 -o /dev/null -w "local443 %{http_code}\n" https://127.0.0.1/auth/login/ -H "Host: delau.tech" || true
