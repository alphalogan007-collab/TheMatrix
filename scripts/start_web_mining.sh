#!/bin/bash
LOG=/tmp/wm_start.txt
exec > "$LOG" 2>&1
echo "=== Web Mining Start ==="

# Write JSON payload to file to avoid shell escaping hell
cat > /tmp/wm_payload.json << 'EOF'
{"queries": [], "use_defaults": true}
EOF

echo "Enqueuing default queries..."
curl -s -X POST http://localhost:8000/admin/web-mining/enqueue \
  -H "Content-Type: application/json" \
  -d @/tmp/wm_payload.json

echo ""
echo "Starting drainer..."
curl -s -X POST http://localhost:8000/admin/web-mining/drain/start

echo ""
echo "Status:"
curl -s http://localhost:8000/admin/web-mining

echo ""
echo "Drain status:"
curl -s http://localhost:8000/admin/web-mining/drain/status

echo "=== Done ==="
