"""Topologia do TP3: clientes -> cadeia de VNFs -> núcleo -> servidores.

    clientes -- s1 -- vnf1 -- vnf2 -- ... -- vnfN -- r1 -- s2 -- servidores

Cada VNF é um contentor Docker com duas interfaces de dados (<nome>-in e
<nome>-out) que encaminha pacotes IP entre elas. A ordem da cadeia, as imagens
e os parâmetros vêm de config/chain.yaml, por isso este módulo faz o papel de
orquestrador: cria os contentores, liga-os, configura os endereços e as rotas
e arranca cada VNF com as variáveis do perfil escolhido.
"""
import json
import os
import subprocess

import yaml

# A ordem importa: mininet.net tem de ser importado antes de mininet.link.
from mininet.net import Containernet  # isort: skip
from mininet.node import OVSSwitch  # isort: skip
from mininet.link import Link  # isort: skip
from mininet.log import info  # isort: skip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(ROOT, "config", "chain.yaml")
HOST_IMAGE = "qosi/host"
ROUTER_IMAGE = "qosi/base"
EXPORTER_PORT = 9100
TARGETS_FILE = os.path.join(ROOT, "monitoring", "targets", "vnfs.json")

# Módulos do kernel usados pelas VNFs (carregados na VM, fora dos contentores).
KERNEL_MODULES = ["nf_tables", "nf_conntrack", "sch_htb", "sch_netem",
                  "sch_ingress", "cls_u32", "act_police"]

FORWARDING = {"net.ipv4.ip_forward": "1",
              "net.ipv4.conf.all.rp_filter": "0",
              "net.ipv4.conf.default.rp_filter": "0"}


def load_config(path=DEFAULT_CONFIG):
    with open(path) as handle:
        return yaml.safe_load(handle)


def gateway(network):
    """Primeiro endereço de uma rede /24 escrita como 'a.b.c.0/24'."""
    return network.split("/")[0].rsplit(".", 1)[0] + ".1"


class QosNet:
    """A rede emulada e as operações sobre a cadeia de VNFs."""

    def __init__(self, config=None):
        self.config = config or load_config()
        self.net = None
        self.vnfs = []       # nós das VNFs, pela ordem da cadeia
        self.addresses = []  # (nó, interface, endereço/prefixo)
        self.routes = []     # (nó, destino, próximo salto)
        self.profile = None

    # ------------------------------------------------------------------ build
    def build(self):
        cfg = self.config
        for module in KERNEL_MODULES:
            # Falha sem consequências quando o módulo já vem embutido no kernel.
            subprocess.run(["modprobe", module], check=False, stderr=subprocess.DEVNULL)

        net = self.net = Containernet(controller=None)
        s1 = net.addSwitch("s1", cls=OVSSwitch, failMode="standalone")
        s2 = net.addSwitch("s2", cls=OVSSwitch, failMode="standalone")
        client_net, server_net = cfg["networks"]["clients"], cfg["networks"]["servers"]

        for name, ip in cfg["clients"].items():
            host = net.addDocker(name, ip=f"{ip}/24", dimage=HOST_IMAGE)
            net.addLink(host, s1)
            self.routes.append((host, "default", gateway(client_net)))
        for name, ip in cfg["servers"].items():
            host = net.addDocker(name, ip=f"{ip}/24", dimage=HOST_IMAGE)
            net.addLink(host, s2)
            self.routes.append((host, "default", gateway(server_net)))

        # Caminho encaminhado: as VNFs pela ordem do ficheiro e, no fim, r1.
        self.vnfs = [net.addDocker(vnf["name"], ip=None, dimage=vnf["image"],
                                   sysctls=FORWARDING) for vnf in cfg["chain"]]
        r1 = net.addDocker("r1", ip=None, dimage=ROUTER_IMAGE, sysctls=FORWARDING)
        path = self.vnfs + [r1]

        first, last = path[0], path[-1]
        net.addLink(s1, first, intfName2=f"{first.name}-in")
        self.addresses.append((first, f"{first.name}-in", f"{gateway(client_net)}/24"))
        net.addLink(last, s2, intfName1=f"{last.name}-out")
        self.addresses.append((last, f"{last.name}-out", f"{gateway(server_net)}/24"))

        for index, (left, right) in enumerate(zip(path, path[1:])):
            left_ip, right_ip = f"10.0.{10 + index}.1", f"10.0.{10 + index}.2"
            net.addLink(left, right, cls=Link,
                        intfName1=f"{left.name}-out", intfName2=f"{right.name}-in")
            self.addresses.append((left, f"{left.name}-out", f"{left_ip}/30"))
            self.addresses.append((right, f"{right.name}-in", f"{right_ip}/30"))
            # Rotas estáticas: clientes para trás, servidores para a frente.
            self.routes.append((left, server_net, right_ip))
            self.routes.append((right, client_net, left_ip))
        return self

    # ------------------------------------------------------------------ start
    def start(self, profile="full"):
        self.net.start()
        for node, intf, address in self.addresses:
            node.cmd(f"ip addr flush dev {intf}")
            node.cmd(f"ip addr add {address} dev {intf}")
            node.cmd(f"ip link set {intf} up")
        for node, destination, via in self.routes:
            node.cmd(f"ip route replace {destination} via {via}")
        # Sem offloads, cada pacote que o tc vê corresponde a um pacote na rede.
        for node in self.net.hosts:
            for intf in node.intfNames():
                node.cmd(f"ethtool -K {intf} tso off gso off gro off 2>/dev/null")
        for vnf in self.vnfs:
            vnf.cmd(f"VNF_NAME={vnf.name} EXPORTER_PORT={EXPORTER_PORT} "
                    "nohup python3 /vnf/exporter.py >/var/log/exporter.log 2>&1 &")
        self.write_prometheus_targets()
        self.set_core()
        if profile:
            self.apply_profile(profile)
        return self

    def set_core(self, delay=None, loss=0):
        """Condições do núcleo (netem em r1, nos dois sentidos): atraso e perdas.

        delay é uma duração do tc (ex.: '20ms'); loss é uma percentagem. Uma
        falha da ligação emula-se com loss=100.
        """
        delay = delay or self.config["core"]["delay"]
        for intf in ("r1-out", "r1-in"):
            self["r1"].cmd(f"tc qdisc replace dev {intf} root netem delay {delay} "
                           f"loss {loss}% limit 1000")

    def write_prometheus_targets(self):
        """Diz ao Prometheus onde estão os exportadores das VNFs."""
        targets = [{"targets": [f"{self.management_ip(vnf.name)}:{EXPORTER_PORT}"],
                    "labels": {"node": vnf.name}} for vnf in self.vnfs]
        os.makedirs(os.path.dirname(TARGETS_FILE), exist_ok=True)
        with open(TARGETS_FILE, "w") as handle:
            json.dump(targets, handle, indent=2)

    def stop(self):
        if self.net:
            self.net.stop()

    # --------------------------------------------------------------- profiles
    def apply_profile(self, profile, extra=None):
        """(Re)configura todas as VNFs com as variáveis do perfil indicado.

        extra permite alterar mais variáveis por cima do perfil: {vnf: {VAR: valor}}.
        """
        info(f"*** perfil '{profile}'\n")
        overrides = {name: dict(env) for name, env in
                     (self.config["profiles"][profile] or {}).items()}
        for name, env in (extra or {}).items():
            overrides.setdefault(name, {}).update(env)
        self.configure(overrides)
        self.profile = profile

    def configure(self, overrides):
        """(Re)arranca as VNFs com alterações às variáveis: {vnf: {VAR: valor}}."""
        for vnf, spec in zip(self.vnfs, self.config["chain"]):
            env = {"ENABLED": 1, "IN_IF": f"{vnf.name}-in", "OUT_IF": f"{vnf.name}-out"}
            env.update(spec.get("env") or {})
            env.update(overrides.get(vnf.name) or {})
            assignments = " ".join(f"{key}='{value}'" for key, value in env.items())
            output = vnf.cmd(f"env {assignments} /vnf/start; echo EXIT=$?").strip()
            info(f"    {vnf.name}: {output}\n")
            if not output.endswith("EXIT=0"):
                raise RuntimeError(f"{vnf.name} falhou ao arrancar:\n{output}")
        self.profile = None

    # ---------------------------------------------------------------- helpers
    def __getitem__(self, name):
        return self.net.get(name)

    def ip(self, name):
        hosts = {**self.config["clients"], **self.config["servers"]}
        return hosts[name]

    def management_ip(self, name):
        """Endereço do nó na rede de gestão (a bridge do Docker)."""
        return self[name].cmd("ip -4 -o addr show dev eth0 | awk '{print $4}'") \
            .strip().split("/")[0]
