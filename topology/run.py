#!/usr/bin/env python3
"""Arranca a topologia do TP3.

Correr como root, a partir da raiz do repositório:

    /opt/containernet/venv/bin/python3 topology/run.py --profile full

Sem mais opções, abre a consola do Mininet. Por exemplo:
    h_voip ping -c 3 10.0.2.11
    h_voip traceroute -n 10.0.2.11
    vnf3 tc -s class show dev vnf3-out

A consola tem dois comandos extra, pensados para a demonstração:
    profile baseline     muda o perfil das VNFs sem reiniciar a topologia
    traffic 20           gera 20 s de tráfego e mostra as métricas medidas
    traffic 20 stress    junta vídeo acima do perfil e tráfego de h_x

Com --demo N, em vez da consola gera durante N segundos a mistura de tráfego
dos testes (VoIP, vídeo e quatro fluxos TCP) e mostra as métricas no fim. É
útil para ver o dashboard do Grafana a mexer; com --stress, o policiador e a
firewall também têm tráfego para descartar.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qosnet import DEFAULT_CONFIG, QosNet, load_config  # noqa: E402
from flows import FLOOD_PORT, VIDEO, VOIP, TcpFlow, UdpFlow  # noqa: E402
from mininet.cli import CLI  # noqa: E402
from mininet.log import setLogLevel  # noqa: E402


def demo(qos, duration, stress=False):
    bulk = TcpFlow(qos, "h_bulk", "srv_bulk", duration=duration, streams=4)
    voip = UdpFlow(qos, "h_voip", "srv_voip", duration=duration, **VOIP)
    # Com stress, o vídeo passa de 4 para 6 Mbit/s (acima do perfil de 5 Mbit/s)
    # e h_x, que não está autorizado, envia 2 Mbit/s.
    video = UdpFlow(qos, "h_video", "srv_video", duration=duration,
                    **dict(VIDEO, pps=600 if stress else VIDEO["pps"]))
    flood = UdpFlow(qos, "h_x", "srv_bulk", port=FLOOD_PORT, pps=200, size=1222,
                    duration=duration) if stress else None
    for name, flow in (("VoIP", voip), ("vídeo", video)):
        r = flow.result()
        print(f"{name:6} OWD média {r['owd_ms_mean']} ms, p95 {r['owd_ms_p95']} ms, "
              f"IPDV média {r['ipdv_ms_mean']} ms, perdas {r['loss_ratio']:.2%}, "
              f"débito {r['throughput_kbps']} kbit/s, "
              f"maior intervalo entre chegadas {r['rx_gap_ms_max']} ms")
    print(f"TCP    débito {bulk.result()['throughput_kbps']} kbit/s")
    if flood:
        r = flood.result()
        print(f"h_x    {r.get('sent')} pacotes enviados, {r.get('received')} entregues")


class DemoCLI(CLI):
    """Consola do Mininet com dois comandos extra, para demonstrações ao vivo."""

    def __init__(self, qos, script=None):
        self.qos = qos
        super().__init__(qos.net, script=script)

    def onecmd(self, line):
        if self.inputFile and line.strip():  # num guião, mostra o comando antes da saída
            print(f"\ncontainernet> {line.strip()}", flush=True)
        return super().onecmd(line)

    def do_profile(self, line):
        "profile <nome>: muda o perfil das VNFs sem reiniciar a topologia"
        name = line.strip()
        if name not in self.qos.config["profiles"]:
            print("perfis: " + ", ".join(self.qos.config["profiles"]))
            return
        self.qos.apply_profile(name)

    def do_traffic(self, line):
        "traffic [segundos] [stress]: gera VoIP, vídeo e 4 fluxos TCP e mostra as métricas"
        words = line.split()
        seconds = next((int(word) for word in words if word.isdigit()), 20)
        print(f"a gerar tráfego durante {seconds} s (perfil {self.qos.profile})...")
        demo(self.qos, seconds, "stress" in words)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--profile", default="full",
                        help="perfil definido em config/chain.yaml (baseline, sched, police, full)")
    parser.add_argument("--demo", type=int, metavar="N",
                        help="gera tráfego durante N segundos em vez de abrir a consola")
    parser.add_argument("--script", metavar="FICHEIRO",
                        help="corre os comandos de consola do ficheiro, um por linha, e sai")
    parser.add_argument("--stress", action="store_true",
                        help="com --demo: junta vídeo acima do perfil e tráfego não autorizado")
    args = parser.parse_args()

    setLogLevel("info" if args.demo is None else "warning")
    qos = QosNet(load_config(args.config)).build()
    try:
        qos.start(args.profile)
        if args.demo is None:
            DemoCLI(qos, script=args.script)
        else:
            demo(qos, args.demo, args.stress)
    finally:
        qos.stop()


if __name__ == "__main__":
    main()
