#!/bin/bash
# Check oscillation status — run after deploy to verify fix
LOG=/tmp/status_log.txt
exec > "$LOG" 2>&1
echo "=== Oscillation Status $(date) ==="

AUTH="-a e7338d82b9bcea35bcd2b35874b39c75 --no-auth-warning"
CLI="docker exec mindai_redis redis-cli $AUTH"

echo -n "space:layer1:  "; $CLI XLEN space:layer1
echo -n "space:layer2:  "; $CLI XLEN space:layer2
echo -n "body:layer13:  "; $CLI XLEN body:layer13
echo -n "digital:layer1: "; $CLI XLEN digital:layer1
echo -n "spirit:events: "; $CLI XLEN spirit:events
echo -n "corpus size:   "; $CLI HLEN guidance:corpus
echo -n "barzakh keys:  "; $CLI KEYS 'barzakh:*' | wc -l
echo "=== Done ==="
