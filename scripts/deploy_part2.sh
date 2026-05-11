#!/bin/bash
LOG=/tmp/deploy_log2.txt
exec > "$LOG" 2>&1
echo "=== Deploy part 2 $(date) ==="

echo "--- Foundation ---"
# Find foundation_mind.py path inside the container
FPATH=$(docker exec thematrix_foundation sh -c "find / -name foundation_mind.py -maxdepth 5 2>/dev/null" | head -1)
echo "Foundation path: $FPATH"
if [ -n "$FPATH" ]; then
  docker cp /tmp/foundation_mind.py "thematrix_foundation:${FPATH}"
  docker restart thematrix_foundation
  echo "OK: thematrix_foundation at $FPATH"
else
  echo "WARN: foundation_mind.py not found inside container"
fi

echo "--- Backend ---"
docker cp /tmp/routes_world.py mindai_prophet:/app/app/api/routes_world.py
docker cp /tmp/routes_web_mining.py mindai_prophet:/app/app/api/routes_web_mining.py
docker cp /tmp/main.py mindai_prophet:/app/app/main.py
docker restart mindai_prophet
echo "OK: mindai_prophet"

echo "--- e_seed-2 (missed earlier) ---"
if docker inspect thematrix-e_seed-2 > /dev/null 2>&1; then
  docker cp /tmp/seed_mind.py thematrix-e_seed-2:/seed/seed_mind.py
  docker restart thematrix-e_seed-2
  echo "OK: thematrix-e_seed-2"
fi
if docker inspect thematrix-nuh_seed-1 > /dev/null 2>&1; then
  docker cp /tmp/seed_mind.py thematrix-nuh_seed-1:/seed/seed_mind.py
  docker restart thematrix-nuh_seed-1
  echo "OK: thematrix-nuh_seed-1"
fi

echo "--- Flush barzakh ---"
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning \
  EVAL "local k=redis.call('keys','barzakh:*') if #k>0 then redis.call('del',unpack(k)) end return #k" 0
echo "Barzakh flushed"

echo "--- Status ---"
echo -n "corpus: "
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning HLEN guidance:corpus
echo -n "space:layer1: "
docker exec mindai_redis redis-cli -a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning XLEN space:layer1

echo "=== Done $(date) ==="
