#!/bin/bash
exec > /tmp/status2.txt 2>&1
echo "=== ALL NON-WORKER CONTAINERS ==="
docker ps --format "{{.Names}} | {{.Status}} | {{.Ports}}" 2>/dev/null | grep -vE 'layer[0-9]' | head -40

echo ""
echo "=== STOPPED CONTAINERS ==="
docker ps -a --format "{{.Names}} | {{.Status}}" 2>/dev/null | grep -iE 'exit|dead|created' | grep -vE 'layer[0-9]' | head -20

echo ""
echo "=== COMPOSE FILES ON EC2 ==="
ls -la /opt/mindai/*.yml 2>/dev/null

echo ""
echo "=== CADDY STATUS ==="
docker ps -a --format "{{.Names}} | {{.Status}} | {{.Ports}}" 2>/dev/null | grep -i caddy

echo ""
echo "=== BACKEND PORT 8000 ==="
docker ps -a --format "{{.Names}} | {{.Status}} | {{.Ports}}" 2>/dev/null | grep 8000

echo ""
echo "=== PORT 80/443 LISTENING ==="
ss -tlnp 2>/dev/null | grep -E ':80|:443' || netstat -tlnp 2>/dev/null | grep -E ':80|:443'
