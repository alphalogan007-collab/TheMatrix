#!/bin/bash
exec > /tmp/deploy_seed2.txt 2>&1
echo "=== Deploying fixed seed_mind.py (direct) ==="

# Known seed containers from live EC2 topology
# Targets: Adam (x2), Eve/prophet (x1), e-ring (x2), prophet rings (x5), ca (x1)
TARGETS="thematrix-seed-1 thematrix-seed-2 thematrix-p_seed-1 thematrix-e_seed-1 thematrix-e_seed-2 thematrix-nuh_seed-1 thematrix-ibrahim_seed-1 thematrix-musa_seed-1 thematrix-isa_seed-1 thematrix-muhammad_seed-1 topo_ca_seed"

for c in $TARGETS; do
  echo "--- $c ---"
  docker cp /tmp/seed_mind.py "$c":/seed/seed_mind.py 2>&1 && echo "  copied OK"
  docker restart "$c" 2>&1 && echo "  restarted OK"
done

echo "=== All done ==="
