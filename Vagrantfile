# -*- mode: ruby -*-
# Ambiente reprodutível do TP3 de QoSI (grupo PL11).
#   vagrant up        -> cria e configura a VM
#   vagrant ssh       -> entra na VM (o repositório fica em /vagrant)
#   vagrant halt      -> desliga a VM
Vagrant.configure("2") do |config|
  config.vm.box = "bento/ubuntu-22.04"
  config.vm.hostname = "qosi"

  # Dashboards acessíveis a partir do Windows (apenas em localhost).
  config.vm.network "forwarded_port", guest: 3000, host: 3000, host_ip: "127.0.0.1" # Grafana
  config.vm.network "forwarded_port", guest: 9090, host: 9090, host_ip: "127.0.0.1" # Prometheus

  config.vm.synced_folder ".", "/vagrant"

  config.vm.provider "virtualbox" do |vb|
    vb.name = "qosi-tp3"
    vb.cpus = 4
    vb.memory = 8192
  end

  config.vm.provision "base", type: "shell", path: "scripts/provision-base.sh"
  config.vm.provision "tex", type: "shell", path: "scripts/provision-tex.sh"
  config.vm.provision "containernet", type: "shell", path: "scripts/provision-containernet.sh"
end
