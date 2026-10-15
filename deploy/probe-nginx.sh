#!/bin/bash
set -uo pipefail
IP=45.130.173.22
echo "--- fail2ban ---"
if command -v fail2ban-client >/dev/null; then
  fail2ban-client status || true
  fail2ban-client banned || true
  echo "--- unban $IP ---"
  fail2ban-client unban "$IP" || true
  fail2ban-client banned || true
else
  echo "no fail2ban"
fi
echo "--- iptables hit ---"
iptables -S | grep -F "$IP" || echo "no iptables rule for $IP"
echo "--- auth ---"
grep -F "$IP" /var/log/auth.log 2>/dev/null | tail -20 || true
grep -F "$IP" /var/log/fail2ban.log 2>/dev/null | tail -20 || true
