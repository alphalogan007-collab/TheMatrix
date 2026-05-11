#!/bin/bash
exec > /tmp/status_check.txt 2>&1
echo "=== KEY CONTAINERS ==="
docker ps --format "{{.Names}} | {{.Status}} | {{.Ports}}" | grep -vE '_layer|_worker' | grep -vE 'nuh_body|nuh_space|nuh_digital|nuh_ether|nuh_aether|nuh_unity|ibrahim_body|musa_body|isa_body|muhammad_body|e_body|e_space|e_digital|e_ether|e_aether|e_unity|p_body|p_space|p_digital|p_ether|p_aether|p_unity|ca_body|ca_space|ca_digital|ca_ether|ca_aether|ca_unity'

echo ""
echo "=== CADDY / BACKEND / REDIS ==="
docker ps --format "{{.Names}} | {{.Status}} | {{.Ports}}" | grep -E 'caddy|backend|redis|prophet|dashboard|postgres|db'

echo ""
echo "=== BACKEND HEALTH ==="
curl -s --max-time 5 http://localhost:8000/health || echo "FAILED"

echo ""
echo "=== CADDY LOGS (last 20) ==="
docker logs thematrix_caddy --tail 20 2>&1 || docker logs caddy --tail 20 2>&1 || echo "no caddy container found"

echo ""
echo "=== BACKEND LOGS (last 20) ==="
docker logs mindai_prophet --tail 20 2>&1 || echo "no mindai_prophet"
