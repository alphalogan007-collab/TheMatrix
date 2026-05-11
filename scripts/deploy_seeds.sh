#!/bin/bash
# Deploy seed_mind.py to all seed containers
OUT=/tmp/deploy_seeds.txt
echo "=== SEED DEPLOY $(date) ===" > $OUT

SEEDS=""
# Check each possible seed container name
for name in thematrix-p_seed-1 thematrix-seed-1 thematrix-seed-2 topo_seed_adam topo_seed_prophet topo_ca_seed; do
    if docker inspect "$name" > /dev/null 2>&1; then
        SEEDS="$SEEDS $name"
        echo "Found: $name" >> $OUT
    fi
done

echo "Seeds to update: $SEEDS" >> $OUT

for c in $SEEDS; do
    docker cp /tmp/seed_mind.py "$c":/seed/seed_mind.py >> $OUT 2>&1 && echo "cp ok: $c" >> $OUT
done

for c in $SEEDS; do
    docker restart "$c" >> $OUT 2>&1 && echo "restarted: $c" >> $OUT
done

echo "=== DONE ===" >> $OUT
cat $OUT
