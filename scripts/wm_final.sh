#!/bin/bash
exec > /tmp/wm_final.txt 2>&1
echo "=== Web Mining Final Start ==="

echo "--- Current web: key count in corpus ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning hkeys guidance:corpus 2>/dev/null | grep -c "^web:" || echo "0"

echo "--- Clear old queue state ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning del web:mining:queue web:mining:done web:mining:dead web:mining:claimed web:mining:status 2>/dev/null

echo "--- Enqueue 32 default queries (run INSIDE container) ---"
docker exec mindai_prophet curl -s -X POST http://localhost:8000/admin/web-mining/enqueue \
  -H "Content-Type: application/json" \
  -d '{"queries": [], "use_defaults": true}'
echo ""

echo "--- Start drainer (run INSIDE container) ---"
docker exec mindai_prophet curl -s -X POST http://localhost:8000/admin/web-mining/drain/start
echo ""

echo "--- Waiting 90s for Wikipedia queries ---"
sleep 90

echo "--- Drain status (run INSIDE container) ---"
docker exec mindai_prophet curl -s http://localhost:8000/admin/web-mining/drain/status
echo ""

echo "--- Queue stats (run INSIDE container) ---"
docker exec mindai_prophet curl -s http://localhost:8000/admin/web-mining
echo ""

echo "--- web: key count in corpus ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning hkeys guidance:corpus 2>/dev/null | grep -c "^web:" || echo "0"

echo "--- Sample web: keys ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning hkeys guidance:corpus 2>/dev/null | grep "^web:" | head -10

echo "=== Done ==="
