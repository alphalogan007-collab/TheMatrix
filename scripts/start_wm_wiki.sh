#!/bin/bash
exec > /tmp/wm_wiki.txt 2>&1
echo "=== Wikipedia Web Mining Start ==="

echo "--- Waiting for backend to be healthy ---"
for i in $(seq 1 20); do
  STATUS=$(curl -s --max-time 5 http://localhost:8000/health 2>/dev/null)
  if echo "$STATUS" | grep -q '"ok"'; then
    echo "Backend healthy after ${i}s"
    break
  fi
  sleep 2
done

echo ""
echo "--- Stop old drainer (if any) ---"
curl -s --max-time 10 -X POST http://localhost:8000/admin/web-mining/drain/stop
echo ""

echo "--- Clear old queue ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning del web:mining:queue web:mining:done web:mining:dead web:mining:claimed 2>/dev/null
echo "Cleared"

echo ""
echo "--- Enqueue 32 default queries ---"
cat > /tmp/wm_payload.json << 'EOF'
{"queries": [], "use_defaults": true}
EOF
curl -s --max-time 15 -X POST http://localhost:8000/admin/web-mining/enqueue \
  -H "Content-Type: application/json" \
  -d @/tmp/wm_payload.json
echo ""

echo "--- Start Wikipedia drainer ---"
curl -s --max-time 10 -X POST http://localhost:8000/admin/web-mining/drain/start
echo ""

echo "--- Waiting 60s for Wikipedia queries to complete ---"
sleep 60

echo "--- Drain status ---"
curl -s --max-time 10 http://localhost:8000/admin/web-mining/drain/status
echo ""

echo "--- Queue depth ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning llen web:mining:queue 2>/dev/null

echo "--- Done count ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning llen web:mining:done 2>/dev/null

echo "--- web: keys in corpus ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning hkeys guidance:corpus 2>/dev/null | grep "^web:" | head -20

echo "--- web: key count ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning hkeys guidance:corpus 2>/dev/null | grep -c "^web:"

echo "--- Recent backend logs ---"
docker logs mindai_prophet --tail 20 2>&1

echo "=== Done ==="
