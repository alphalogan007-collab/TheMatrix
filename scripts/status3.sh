#!/bin/bash
exec > /tmp/status3.txt 2>&1
echo "=== ALL RUNNING CONTAINERS ==="
docker ps --format "{{.Names}} | {{.Status}} | {{.Ports}}"

echo ""
echo "=== ALL STOPPED/EXITED ==="
docker ps -a --format "{{.Names}} | {{.Status}}" | grep -v "Up "

echo ""
echo "=== PORTS 80 443 ==="
ss -tlnp | grep -E ':80 |:443 '

echo ""
echo "=== COMPOSE FILES ==="
ls /opt/mindai/*.yml
