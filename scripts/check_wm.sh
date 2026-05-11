#!/bin/bash
exec > /tmp/wm_check.txt 2>&1
echo "=== Web Mining Check ==="
echo "--- Backend health ---"
curl -s --max-time 10 http://localhost:8000/health
echo ""
echo "--- Drain status ---"
curl -s --max-time 10 http://localhost:8000/admin/web-mining/drain/status
echo ""
echo "--- Queue stats ---"
curl -s --max-time 10 http://localhost:8000/admin/web-mining
echo ""
echo "--- web: keys in corpus ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning hkeys guidance:corpus 2>/dev/null | grep "^web:" | head -20
echo "--- web: key count ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning hkeys guidance:corpus 2>/dev/null | grep -c "^web:"
echo "=== Done ==="
