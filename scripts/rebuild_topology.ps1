#!/usr/bin/env pwsh
# rebuild_topology.ps1 — Full rebuild and start of the triadic mind topology
# Run from C:\DEV\MindAI

Set-Location "C:\DEV\MindAI"

Write-Host "=== Step 1: Regenerate cluster compose ===" -ForegroundColor Cyan
docker run --rm -v "${PWD}:/app" python:3.11-alpine python /app/topology/scaler/gen_cluster_compose.py > infra/docker-compose.cluster.yml
if ($LASTEXITCODE -ne 0) { Write-Error "Cluster compose generation failed"; exit 1 }
Write-Host "Cluster compose regenerated: $((Get-Content infra/docker-compose.cluster.yml | Measure-Object -Line).Lines) lines"

Write-Host "=== Step 2: Build seed image ===" -ForegroundColor Cyan
docker compose -f infra/docker-compose.topology.yml build seed
if ($LASTEXITCODE -ne 0) { Write-Error "Seed build failed"; exit 1 }

Write-Host "=== Step 3: Build node image ===" -ForegroundColor Cyan
docker compose -f infra/docker-compose.topology.yml build body_layer1
if ($LASTEXITCODE -ne 0) { Write-Error "Node build failed"; exit 1 }

Write-Host "=== Step 4: Start topology (seed + body) ===" -ForegroundColor Cyan
docker compose -f infra/docker-compose.topology.yml up -d --force-recreate
if ($LASTEXITCODE -ne 0) { Write-Warning "Some containers may not have started cleanly" }

Write-Host "=== Step 5: Build cluster (prophet) image ===" -ForegroundColor Cyan
docker compose -f infra/docker-compose.cluster.yml build p_seed p_body_layer1 p_unity_layer1
if ($LASTEXITCODE -ne 0) { Write-Error "Cluster build failed"; exit 1 }

Write-Host "=== Step 6: Start prophet soul ===" -ForegroundColor Cyan
$prophetServices = docker compose -f infra/docker-compose.cluster.yml config --services | Select-String "^p_" | ForEach-Object { $_.Line }
docker compose -f infra/docker-compose.cluster.yml up -d $prophetServices
if ($LASTEXITCODE -ne 0) { Write-Warning "Some prophet containers may not have started cleanly" }

Write-Host "=== Step 7: Health check ===" -ForegroundColor Cyan
Start-Sleep -Seconds 5
$running = docker ps --format "{{.Names}}: {{.Status}}" | Select-String "infra-" | Measure-Object
Write-Host "Running containers: $($running.Count)"
docker ps --format "{{.Names}}: {{.Status}}" | Select-String "Exit|unhealthy"

Write-Host "=== Step 8: Smoke test — inject into seed:input ===" -ForegroundColor Cyan
$testMsg = "What is consciousness and how does it arise from the substrate of reality?"
docker exec mindai_redis redis-cli -a changeme_redis_dev XADD "seed:input" "*" `
    content $testMsg `
    input_type "text" `
    source "smoke_test" `
    session_id "smoke_001"

Write-Host "=== Watching for events (10 seconds) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 3
docker exec mindai_redis redis-cli -a changeme_redis_dev XREVRANGE "spirit:events" + - COUNT 10

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host "Check logs: docker logs infra-seed-1 --tail 20"
Write-Host "Check events: docker exec mindai_redis redis-cli -a changeme_redis_dev XREVRANGE spirit:events + - COUNT 20"
