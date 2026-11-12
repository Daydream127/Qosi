#!/usr/bin/env bash
# Limpa os restos de uma topologia que não terminou bem: processos de teste,
# contentores do Containernet (mn.*), interfaces e switches do Mininet.
set -uo pipefail

pkill -f "topology/run.py" 2>/dev/null
pkill -f "tests/test_vnfs.py" 2>/dev/null
pkill -f "experiments/" 2>/dev/null
sleep 1
/opt/containernet/venv/bin/mn -c >/dev/null 2>&1
docker ps -aq --filter "name=mn." | xargs -r docker rm -f >/dev/null
echo "contentores mn.* restantes: $(docker ps -aq --filter 'name=mn.' | wc -l)"
