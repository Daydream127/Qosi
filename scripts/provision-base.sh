#!/usr/bin/env bash
# Ferramentas base da VM: rede, geração de tráfego e utilitários.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install -y --no-install-recommends \
  git curl ca-certificates make \
  python3 python3-pip python3-venv \
  iproute2 iputils-ping traceroute tcpdump nftables \
  iperf3 ansible

echo "provision-base: ok"
