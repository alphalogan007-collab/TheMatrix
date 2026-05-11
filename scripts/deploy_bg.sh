#!/bin/bash
LOG=/tmp/deploy_log.txt
exec > "$LOG" 2>&1
echo "=== Deploy $(date) ==="

# Seed containers — path: /seed/seed_mind.py
echo "--- Seed containers ---"
for CNAME in thematrix-seed-1 thematrix-seed-2 thematrix-p_seed-1 \
             thematrix-e_seed-1 thematrix-e_seed-2 \
             thematrix-nuh_seed-1 thematrix-ibrahim_seed-1 \
             thematrix-musa_seed-1 thematrix-isa_seed-1 \
             thematrix-muhammad_seed-1 topo_ca_seed; do
  if docker inspect "$CNAME" > /dev/null 2>&1; then
    docker cp /tmp/seed_mind.py "$CNAME":/seed/seed_mind.py
    docker restart "$CNAME"
    echo "OK: $CNAME"
  fi
done

echo "--- Foundation ---"
FPATH=$(docker exec thematrix_foundation find / -name "foundation_mind.py" -maxdepth 5 2>/dev/null | head -1)
echo "Foundation file at: $FPATH"
if [ -n "$FPATH" ]; then
  docker cp /tmp/foundation_mind.py thematrix_foundation:"$FPATH"
  docker restart thematrix_foundation
  echo "OK: thematrix_foundation"
fi

echo "--- Backend ---"
docker cp /tmp/routes_world.py mindai_prophet:/app/app/api/routes_world.py
docker cp /tmp/routes_web_mining.py mindai_prophet:/app/app/api/routes_web_mining.py
docker cp /tmp/main.py mindai_prophet:/app/app/main.py
docker restart mindai_prophet
echo "OK: mindai_prophet"

echo "--- Flush barzakh ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning \
  EVAL "local k=redis.call('keys','barzakh:*') if #k>0 then redis.call('del',unpack(k)) end return #k" 0
echo "Barzakh flushed"

echo "--- Status ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning HLEN guidance:corpus
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning XLEN space:layer1
echo "=== Done $(date) ==="

echo "=== Deploy finished $(date) ==="
