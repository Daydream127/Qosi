#!/usr/bin/env python3
"""Arranca a topologia do TP3.

Correr como root, a partir da raiz do repositório:

    /opt/containernet/venv/bin/python3 topology/run.py --profile full

Sem mais opções, abre a consola do Mininet. Por exemplo:
    h_voip ping -c 3 10.0.2.11
    h_voip traceroute -n 10.0.2.11
    vnf3 tc -s class show dev vnf3-out

Com --demo N, em vez da consola gera durante N segundos a mistura de tráfego
dos testes (VoIP, vídeo e quatro fluxos TCP) e mostra as métricas no fim. É
útil para ver o dashboard do Grafana a mexer.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qosnet import DEFAULT_CONFIG, QosNet, load_config  # noqa: E402
from flows import VIDEO, VOIP, TcpFlow, UdpFlow  # noqa: E402
from mininet.cli import CLI  # noqa: E402
from mininet.log import setLogLevel  # noqa: E402


def demo(qos, duration):
    bulk = TcpFlow(qos, "h_bulk", "srv_bulk", duration=duration, streams=4)
    voip = UdpFlow(qos, "h_voip", "srv_voip", duration=duration, **VOIP)
    video = UdpFlow(qos, "h_video", "srv_video", duration=duration, **VIDEO)
    for name, flow in (("VoIP", voip), ("vídeo", video)):
        r = flow.result()
        print(f"{name:6} OWD média {r['owd_ms_mean']} ms, p95 {r['owd_ms_p95']} ms, "
              f"IPDV média {r['ipdv_ms_mean']} ms, perdas {r['loss_ratio']:.2%}, "
              f"débito {r['throughput_kbps']} kbit/s")
    print(f"TCP    débito {bulk.result()['throughput_kbps']} kbit/s")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--profile", default="full",
                        help="perfil definido em config/chain.yaml (baseline, sched, police, full)")
    parser.add_argument("--demo", type=int, metavar="N",
                        help="gera tráfego durante N segundos em vez de abrir a consola")
    args = parser.parse_args()

    setLogLevel("info" if args.demo is None else "warning")
    qos = QosNet(load_config(args.config)).build()
    try:
        qos.start(args.profile)
        if args.demo is None:
            CLI(qos.net)
        else:
            demo(qos, args.demo)
    finally:
        qos.stop()


if __name__ == "__main__":
    main()
