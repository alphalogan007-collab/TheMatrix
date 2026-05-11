#!/bin/bash
exec > /tmp/wm_restart.txt 2>&1
echo "=== Backend logs (last 50 lines) ==="
docker logs mindai_prophet --tail 50 2>&1

echo ""
echo "=== Clear queue and re-enqueue all 32 ==="
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning del web:mining:queue web:mining:done web:mining:dead web:mining:claimed 2>/dev/null
echo "Queue cleared"

echo ""
echo "=== Re-enqueue ==="
cat > /tmp/wm_payload.json << 'EOF'
{"queries": [], "use_defaults": true}
EOF
curl -s --max-time 15 -X POST http://localhost:8000/admin/web-mining/enqueue \
  -H "Content-Type: application/json" \
  -d @/tmp/wm_payload.json
echo ""

echo "=== Start drainer ==="
curl -s --max-time 10 -X POST http://localhost:8000/admin/web-mining/drain/start
echo ""

echo "=== Waiting 30s for first queries to process ==="
sleep 30

echo "=== Drain status ==="
curl -s --max-time 10 http://localhost:8000/admin/web-mining/drain/status
echo ""

echo "=== Queue depth ==="
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning llen web:mining:queue 2>/dev/null

echo "=== Done count ==="
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning llen web:mining:done 2>/dev/null

echo "=== web: keys in corpus ==="
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning hkeys guidance:corpus 2>/dev/null | grep "^web:" | head -10

echo "=== Done ==="
