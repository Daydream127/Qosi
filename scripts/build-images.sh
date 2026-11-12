#!/usr/bin/env bash
# Constrói as imagens Docker de todos os nós da topologia.
set -euo pipefail
cd "$(dirname "$0")/.."

docker build -q -t qosi/base vnfs/base
docker build -q -t qosi/host traffic
for vnf in classifier firewall qos monitor; do
  docker build -q -f "vnfs/$vnf/Dockerfile" -t "qosi/$vnf" vnfs
done
docker images --format '{{.Repository}}\t{{.Size}}' | grep '^qosi/' | sort
