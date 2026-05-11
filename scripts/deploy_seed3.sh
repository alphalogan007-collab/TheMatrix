#!/bin/bash
exec > /tmp/deploy_seed3.txt 2>&1
echo "=== Deploying to e-ring and prophet ring seeds ==="

# Confirm source file exists
ls -la /tmp/seed_mind.py || { echo "ERROR: /tmp/seed_mind.py missing"; exit 1; }

REMAINING="thematrix-e_seed-1 thematrix-e_seed-2 thematrix-nuh_seed-1 thematrix-ibrahim_seed-1 thematrix-musa_seed-1 thematrix-isa_seed-1 thematrix-muhammad_seed-1 topo_ca_seed"

for c in $REMAINING; do
  echo "--- $c ---"
  docker cp /tmp/seed_mind.py "$c":/seed/seed_mind.py && echo "  copied OK" || echo "  COPY FAILED"
  docker restart "$c" && echo "  restarted OK" || echo "  RESTART FAILED"
done

echo "=== All done ==="
