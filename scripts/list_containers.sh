#!/bin/bash
docker container ls --no-trunc 2>&1 | awk '{print $NF}' | grep -E "seed|foundation|prophet" | sort
