#!/bin/bash
exec > /tmp/web_status.txt 2>&1

echo "=== NGINX ==="
docker ps -a --format "{{.Names}} | {{.Status}} | {{.Ports}}" --filter name=mindai_nginx

echo ""
echo "=== PROPHET ==="
docker ps -a --format "{{.Names}} | {{.Status}} | {{.Ports}}" --filter name=mindai_prophet

echo ""
echo "=== REDIS ==="
docker ps -a --format "{{.Names}} | {{.Status}}" --filter name=mindai_redis

echo ""
echo "=== PORT 80/443 LISTENING ==="
ss -tlnp | grep -E ':80 |:443 '

echo ""
echo "=== NGINX LOGS (last 10) ==="
docker logs mindai_nginx --tail 10 2>&1

echo ""
echo "=== PROPHET LOGS (last 10) ==="
docker logs mindai_prophet --tail 10 2>&1
