#!/bin/bash
set -euo pipefail

install -m 644 /opt/math-tutor/deploy/math-tutor.service /etc/systemd/system/math-tutor.service
install -m 644 /opt/math-tutor/deploy/math-tutor.nginx.conf /www/server/panel/vhost/nginx/math-tutor.conf
chmod 600 /opt/math-tutor/backend/.env

env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY \
  /opt/math-tutor/venv/bin/pip install -q -r /opt/math-tutor/backend/requirements.txt

systemctl daemon-reload
systemctl enable --now math-tutor
nginx -t
nginx -s reload
ufw allow 19300/tcp

echo "ACTIVE_TUTOR=$(systemctl is-active math-tutor)"
curl -sS http://127.0.0.1:8300/health
echo
