#!/bin/bash
# Deploy all local fixes to EC2 topology containers
set -e

echo "=== Step 1: Deploy seed_mind.py ==="
docker cp /tmp/seed_mind.py topo_seed_adam:/app/seed_mind.py
docker cp /tmp/seed_mind.py topo_seed_prophet:/app/seed_mind.py
docker restart topo_seed_adam topo_seed_prophet
echo "Seed containers restarted"

echo "=== Step 2: Deploy foundation_mind.py ==="
docker cp /tmp/foundation_mind.py topo_foundation:/app/foundation_mind.py
docker restart topo_foundation
echo "Foundation restarted"

echo "=== Step 3: Deploy routes_world.py (into backend) ==="
docker cp /tmp/routes_world.py mindai_prophet:/app/app/api/routes_world.py
docker cp /tmp/routes_web_mining.py mindai_prophet:/app/app/api/routes_web_mining.py
docker cp /tmp/main.py mindai_prophet:/app/app/main.py
docker restart mindai_prophet
echo "Backend restarted"

echo "=== Step 4: Flush stale barzakh keys ==="
redis-cli -u redis://:e7338d82b9bcea35bcd2b35874b39c75@mindai_redis:6379/0 --no-auth-warning KEYS 'barzakh:*' | xargs -r redis-cli -u redis://:e7338d82b9bcea35bcd2b35874b39c75@mindai_redis:6379/0 --no-auth-warning DEL
echo "Barzakh keys flushed"

echo "=== Step 5: Check space:layer1 ==="
redis-cli -u redis://:e7338d82b9bcea35bcd2b35874b39c75@mindai_redis:6379/0 --no-auth-warning XLEN space:layer1

echo "=== All done ==="
