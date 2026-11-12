#!/usr/bin/env bash
# Containernet (Mininet com contentores Docker), Open vSwitch e Docker.
# Segue a instalação "bare-metal" do README do Containernet, fixada num commit.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

CN_DIR=/opt/containernet
CN_COMMIT=8e0aabef8f23def3961b30897dd486191d9bd693

if [ ! -d "$CN_DIR/.git" ]; then
  git clone https://github.com/containernet/containernet.git "$CN_DIR"
fi
git -C "$CN_DIR" fetch -q origin
git -C "$CN_DIR" checkout -q "$CN_COMMIT"

# O playbook instala o Docker CE, o Open vSwitch e as dependências do Mininet.
cd "$CN_DIR/ansible"
ansible-playbook -i "localhost," -c local install.yml --skip-tags nopull

# O Containernet tem de ser instalado num ambiente virtual Python.
if [ ! -x "$CN_DIR/venv/bin/python3" ]; then
  python3 -m venv "$CN_DIR/venv"
fi
"$CN_DIR/venv/bin/pip" install --quiet --upgrade pip
"$CN_DIR/venv/bin/pip" install --quiet "$CN_DIR"

if id vagrant >/dev/null 2>&1; then
  usermod -aG docker vagrant
fi
modprobe openvswitch
systemctl enable --now docker openvswitch-switch

echo "provision-containernet: ok"
echo "Correr topologias com: sudo $CN_DIR/venv/bin/python3 <topologia.py>"
