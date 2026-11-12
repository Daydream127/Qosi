#!/usr/bin/env python3
"""Teste de fumo do ambiente: dois contentores Docker ligados por um switch OVS.

Confirma que o Containernet, o Docker e o Open vSwitch funcionam em conjunto e
que o `tc` consegue limitar uma ligação. Correr dentro da VM:

    sudo /opt/containernet/venv/bin/python3 tests/smoke_test.py
"""
import re
import sys

# A ordem importa: mininet.net tem de ser importado primeiro, senão o
# Containernet falha com um import circular entre mininet.link e mininet.node.
from mininet.net import Containernet  # isort: skip
from mininet.node import OVSSwitch  # isort: skip
from mininet.link import TCLink  # isort: skip
from mininet.log import info, setLogLevel  # isort: skip

IMAGE = "qosi/base"
LINK_MBIT = 10


def main():
    net = Containernet(controller=None)
    h1 = net.addDocker("h1", ip="10.0.0.1/24", dimage=IMAGE)
    h2 = net.addDocker("h2", ip="10.0.0.2/24", dimage=IMAGE)
    s1 = net.addSwitch("s1", cls=OVSSwitch, failMode="standalone")
    net.addLink(h1, s1, cls=TCLink, bw=LINK_MBIT)
    net.addLink(h2, s1)

    ok = True
    net.start()
    try:
        loss = net.ping([h1, h2])
        info(f"*** perda no ping: {loss}%\n")
        ok = ok and loss == 0

        h2.cmd("iperf3 -s -D")
        out = h1.cmd("iperf3 -c 10.0.0.2 -t 5 -f m")
        match = re.search(r"([\d.]+) Mbits/sec\s+receiver", out)
        rate = float(match.group(1)) if match else None
        info(f"*** débito TCP numa ligação de {LINK_MBIT} Mbit/s: {rate} Mbit/s\n")
        ok = ok and rate is not None and 0.5 * LINK_MBIT <= rate <= 1.2 * LINK_MBIT
    finally:
        net.stop()

    print("SMOKE TEST: OK" if ok else "SMOKE TEST: FALHOU")
    return 0 if ok else 1


if __name__ == "__main__":
    setLogLevel("info")
    sys.exit(main())
