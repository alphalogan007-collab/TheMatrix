#!/bin/bash
# Check the working directory inside a seed container
docker exec thematrix-seed-1 ls / > /tmp/check_log.txt 2>&1
docker exec thematrix-seed-1 find / -name "seed_mind.py" -maxdepth 5 >> /tmp/check_log.txt 2>&1
echo "done"
