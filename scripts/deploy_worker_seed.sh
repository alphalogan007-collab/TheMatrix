#!/bin/bash
# Deploy worker.py to all worker containers, seed_mind.py to all seed containers,
# routes_world.py to mindai_prophet. Then restart seeds and prophet.

set -e
OUT=/tmp/deploy_worker_seed.txt
echo "=== DEPLOY $(date) ===" > $OUT

# --- worker.py: copy into every running container that has /app/worker.py ---
WORKERS=$(docker ps --format "{{.Names}}" | grep -E "_body_|_space_|_digital_|_ether_|_aether_|_unity_" | grep -v seed)
echo "Workers found: $(echo "$WORKERS" | wc -l)" >> $OUT
COPIED=0
for c in $WORKERS; do
  docker cp /tmp/worker.py "$c:/app/worker.py" 2>/dev/null && COPIED=$((COPIED+1))
done
echo "worker.py copied into $COPIED containers" >> $OUT

# --- Also copy into thematrix_foundation if it exists and uses worker.py ---
# foundation uses its own file, skip

# --- seed_mind.py: copy into seed containers ---
SEEDS=$(docker ps --format "{{.Names}}" | grep -E "topo_seed|_seed_")
echo "Seeds: $SEEDS" >> $OUT
for c in $SEEDS; do
  docker cp /tmp/seed_mind.py "$c:/app/seed_mind.py" 2>/dev/null && echo "  seed_mind.py → $c" >> $OUT
done

# --- routes_world.py → mindai_prophet ---
docker cp /tmp/routes_world.py mindai_prophet:/app/app/api/routes_world.py 2>/dev/null && echo "routes_world.py → mindai_prophet" >> $OUT

# --- Restart seeds (small footprint) ---
for c in $SEEDS; do
  docker restart "$c" >> $OUT 2>&1 && echo "  restarted $c" >> $OUT
done

# --- Restart prophet + nginx ---
docker restart mindai_prophet >> $OUT 2>&1 && echo "restarted mindai_prophet" >> $OUT
sleep 4
docker restart mindai_nginx >> $OUT 2>&1 && echo "restarted mindai_nginx" >> $OUT

# Workers pick up the new file on next restart — they are stateless and restart on their own cycle.
# Force restart one per domain to flush (layer1 of each):
for dom in body space digital ether aether unity; do
  C=$(docker ps --format "{{.Names}}" | grep "_${dom}_layer1" | head -1)
  if [ -n "$C" ]; then
    docker restart "$C" >> $OUT 2>&1 && echo "  restarted $C" >> $OUT
  fi
done
# Eve ring layer1s
for dom in body space digital ether aether unity; do
  C=$(docker ps --format "{{.Names}}" | grep "p_${dom}_layer1\|_p:${dom}\|p-${dom}_layer1" | head -1)
  if [ -n "$C" ]; then
    docker restart "$C" >> $OUT 2>&1 && echo "  restarted $C (eve)" >> $OUT
  fi
done

echo "=== DONE ===" >> $OUT
cat $OUT
