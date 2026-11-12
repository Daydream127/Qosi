#!/usr/bin/env bash
# Instala tudo o que o projeto precisa num Ubuntu 22.04 (WSL2 ou VM).
# Correr como root, a partir de qualquer pasta:
#   sudo bash scripts/provision-all.sh
set -euo pipefail
cd "$(dirname "$0")"

bash provision-base.sh
bash provision-containernet.sh
bash provision-tex.sh
echo "provision-all: ok"
