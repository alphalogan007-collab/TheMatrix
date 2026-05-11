#!/bin/bash
# Full deploy + discovery script — saves output to /tmp/deploy_log.txt
LOG=/tmp/deploy_log.txt
exec > "$LOG" 2>&1
set -x

echo "=== Container discovery ==="
docker ps -a --filter "name=seed" --no-trunc | cat
docker ps -a --filter "name=foundation" --no-trunc | cat
docker ps -a --filter "name=prophet" --no-trunc | cat

echo ""
echo "=== All running containers (names only via inspect) ==="
docker ps -q | xargs docker inspect --format='{{.Name}}' 2>/dev/null | sort | cat

echo ""
echo "=== Deploy seed_mind.py ==="
# Try known names first, then discover
for CNAME in topo_seed_adam thematrix-topo_seed_adam-1 thematrix_topo_seed_adam_1; do
  if docker inspect "$CNAME" >/dev/null 2>&1; then
    docker cp /tmp/seed_mind.py "$CNAME":/app/seed_mind.py && echo "Copied to $CNAME"
    docker restart "$CNAME" && echo "Restarted $CNAME"
    ADAM_FOUND="$CNAME"
    break
  fi
done
[ -z "$ADAM_FOUND" ] && echo "WARNING: topo_seed_adam equivalent not found"

for CNAME in topo_seed_prophet thematrix-topo_seed_prophet-1 thematrix_topo_seed_prophet_1; do
  if docker inspect "$CNAME" >/dev/null 2>&1; then
    docker cp /tmp/seed_mind.py "$CNAME":/app/seed_mind.py && echo "Copied to $CNAME"
    docker restart "$CNAME" && echo "Restarted $CNAME"
    PROPHET_FOUND="$CNAME"
    break
  fi
done
[ -z "$PROPHET_FOUND" ] && echo "WARNING: topo_seed_prophet equivalent not found"

echo ""
echo "=== Deploy foundation_mind.py ==="
for CNAME in topo_foundation thematrix-topo_foundation-1 thematrix_topo_foundation_1; do
  if docker inspect "$CNAME" >/dev/null 2>&1; then
    docker cp /tmp/foundation_mind.py "$CNAME":/app/foundation_mind.py && echo "Copied to $CNAME"
    docker restart "$CNAME" && echo "Restarted $CNAME"
    FOUND_FOUND="$CNAME"
    break
  fi
done
[ -z "$FOUND_FOUND" ] && echo "WARNING: topo_foundation equivalent not found"

echo ""
echo "=== Deploy backend (mindai_prophet) ==="
for CNAME in mindai_prophet thematrix-mindai_prophet-1; do
  if docker inspect "$CNAME" >/dev/null 2>&1; then
    docker cp /tmp/routes_world.py "$CNAME":/app/app/api/routes_world.py && echo "Copied routes_world.py to $CNAME"
    docker cp /tmp/routes_web_mining.py "$CNAME":/app/app/api/routes_web_mining.py && echo "Copied routes_web_mining.py to $CNAME"
    docker cp /tmp/main.py "$CNAME":/app/app/main.py && echo "Copied main.py to $CNAME"
    docker restart "$CNAME" && echo "Restarted $CNAME"
    BACKEND_FOUND="$CNAME"
    break
  fi
done
[ -z "$BACKEND_FOUND" ] && echo "WARNING: mindai_prophet not found"

echo ""
echo "=== Flush stale barzakh keys ==="
REDIS_URL="redis://:e7338d82b9bcea35bcd2b35874b39c75@mindai_redis:6379/0"
BARZAKH_KEYS=$(redis-cli -u "$REDIS_URL" --no-auth-warning KEYS 'barzakh:*' 2>/dev/null | wc -l)
echo "Barzakh keys found: $BARZAKH_KEYS"
redis-cli -u "$REDIS_URL" --no-auth-warning EVAL "local keys = redis.call('keys','barzakh:*') if #keys > 0 then redis.call('del', unpack(keys)) end return #keys" 0 2>/dev/null && echo "Barzakh keys flushed"

echo ""
echo "=== Corpus check ==="
redis-cli -u "$REDIS_URL" --no-auth-warning HLEN guidance:corpus 2>/dev/null | cat
echo "space:layer1 length:"
redis-cli -u "$REDIS_URL" --no-auth-warning XLEN space:layer1 2>/dev/null | cat

echo ""
echo "=== DONE ==="
