#!/bin/bash
# Find seed containers and deploy seed_mind.py
OUT=/tmp/deploy_seeds.txt
echo "=== SEED DEPLOY $(date) ===" > $OUT

# Show all non-worker containers
echo "--- All non-worker containers ---" >> $OUT
docker ps --format "{{.Names}}" | grep -v "_body_\|_space_\|_digital_\|_ether_\|_aether_\|_unity_" >> $OUT

echo "--- done ---" >> $OUT
cat $OUT
