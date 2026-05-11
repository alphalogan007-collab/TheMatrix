#!/bin/bash
exec > /tmp/deploy_seed.txt 2>&1
echo "=== Deploying fixed seed_mind.py ==="

# Find seed containers
echo "--- Seed containers ---"
docker ps --filter ancestor=thematrix-seed --format "table {{.Names}}\t{{.Status}}" 2>/dev/null
docker ps --no-trunc --format "{{.Names}}" 2>/dev/null | grep -i seed || true

# Try known names from ec2-topology.yml container_name fields
SEEDS="topo_seed_adam topo_seed_prophet thematrix-seed-1 thematrix-seed-2 thematrix-p_seed-1"

for c in $SEEDS; do
  if docker inspect "$c" > /dev/null 2>&1; then
    echo "Found: $c"
    docker cp /tmp/seed_mind.py "$c":/app/seed_mind.py && echo "  Copied to $c"
    docker restart "$c" && echo "  Restarted $c"
  fi
done

echo "--- Done ---"
