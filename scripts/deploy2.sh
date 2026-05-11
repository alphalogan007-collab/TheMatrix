#!/bin/bash
OUT=/tmp/deploy2.txt
echo "=== DEPLOY2 $(date) ===" > $OUT

# worker.py → /worker/worker.py in all worker containers
WORKERS=$(docker ps --format "{{.Names}}" | grep -E "_body_|_space_|_digital_|_ether_|_aether_|_unity_" | grep -v seed)
COPIED=0
for c in $WORKERS; do
  docker cp /tmp/worker.py "$c:/worker/worker.py" 2>>"$OUT" && COPIED=$((COPIED+1))
done
echo "worker.py copied into $COPIED containers" >> $OUT

# seed_mind.py → /seed/seed_mind.py in all seed containers
SEEDS=$(docker ps --format "{{.Names}}" | grep -E "topo_seed|_seed_mind")
echo "Seeds found: $SEEDS" >> $OUT
for c in $SEEDS; do
  docker cp /tmp/seed_mind.py "$c:/seed/seed_mind.py" 2>>"$OUT" && echo "seed ok: $c" >> $OUT
done

# routes_world.py → prophet
docker cp /tmp/routes_world.py mindai_prophet:/app/app/api/routes_world.py >> $OUT 2>&1
echo "routes_world.py → prophet" >> $OUT

# Restart seeds
for c in $SEEDS; do
  docker restart "$c" >> $OUT 2>&1 && echo "restarted $c" >> $OUT
done

# Restart prophet + nginx
docker restart mindai_prophet >> $OUT 2>&1 && echo "restarted mindai_prophet" >> $OUT
sleep 5
docker restart mindai_nginx >> $OUT 2>&1 && echo "restarted mindai_nginx" >> $OUT

# Restart one layer1 worker per domain (adam + eve rings) to pick up new worker.py
for dom in body space digital ether aether unity; do
  C=$(docker ps --format "{{.Names}}" | grep "_${dom}_layer1" | grep -v "_p_" | head -1)
  [ -n "$C" ] && docker restart "$C" >> $OUT 2>&1 && echo "restarted $C" >> $OUT
  CP=$(docker ps --format "{{.Names}}" | grep "_p_${dom}_layer1\|p-${dom}_layer1" | head -1)
  [ -n "$CP" ] && docker restart "$CP" >> $OUT 2>&1 && echo "restarted $CP" >> $OUT
done

echo "=== DONE ===" >> $OUT
cat $OUT
