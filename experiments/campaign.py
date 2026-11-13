#!/usr/bin/env python3
"""Campanha de experiências do TP3.

Corre todos os cenários, com repetições, e grava uma linha por fluxo e por
corrida em results/<conjunto>/runs.csv. Correr como root, na raiz do repositório:

    /opt/containernet/venv/bin/python3 experiments/campaign.py --set quick
    /opt/containernet/venv/bin/python3 experiments/campaign.py --set full

O conjunto "quick" (corridas de 15 s, 2 repetições) serve para validar tudo em
menos de uma hora; o "full" (60 s, 5 repetições) é o da proposta. A campanha
pode ser interrompida e retomada: as corridas já gravadas não são repetidas.

Cenários (ver a função points):
  load      carga crescente: número de fluxos TCP em concorrência
  policing  fonte de vídeo que excede o perfil contratado
  flood     tráfego UDP não autorizado a partir de h_x
  delay     atraso na ligação ao núcleo
  loss      perdas na ligação ao núcleo
  outage    falha temporária da ligação ao núcleo
  queue     otimização: tamanho das filas do gargalo
  weights   otimização: pesos de AF31 e BE
  overhead  sobrecarga da cadeia face ao encaminhamento direto
"""
import argparse
import copy
import csv
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "topology"))

from qosnet import ROOT, QosNet, load_config  # noqa: E402
from flows import BE_PROBE, FLOOD_PORT, VIDEO, VOIP, TcpFlow, UdpFlow  # noqa: E402
from mininet.log import setLogLevel  # noqa: E402

SETS = {"smoke": {"duration": 5, "reps": 1},     # só para testar a própria campanha
        "quick": {"duration": 15, "reps": 2},
        "full": {"duration": 60, "reps": 5}}

COLUMNS = ["timestamp", "experiment", "profile", "x", "rep", "flow", "duration_s",
           "sent", "received", "loss_ratio", "owd_ms_mean", "owd_ms_min", "owd_ms_p50",
           "owd_ms_p95", "owd_ms_p99", "owd_ms_max", "ipdv_ms_mean", "ipdv_ms_p95",
           "jitter_rfc3550_ms", "throughput_kbps", "rx_gap_ms_max", "retransmits"]

VIDEO_PACKET_BITS = (VIDEO["size"] + 28) * 8


def point(experiment, profile, x, **options):
    """Uma corrida: um cenário, um perfil e um valor do parâmetro em estudo."""
    base = {"experiment": experiment, "profile": profile, "x": x,
            "chain": "default",      # "default" ou "none" (encaminhamento direto)
            "tcp_streams": 4, "voip": True, "video_mbit": 4, "be_probe": True,
            "flood_mbit": 0,
            "overrides": {},         # alterações às variáveis das VNFs
            "core": {},              # delay e loss da ligação ao núcleo
            "outage_s": 0,           # duração de uma falha a meio da corrida
            "packets": False}        # guardar as amostras por pacote do VoIP
    base.update(options)
    return base


def points():
    """Lista de todas as corridas da campanha (sem contar as repetições)."""
    runs = []

    for streams in (0, 1, 2, 4, 8):
        for profile in ("baseline", "sched", "police", "full"):
            runs.append(point("load", profile, streams, tcp_streams=streams))

    for mbit in (4, 6, 8, 12):
        for profile in ("baseline", "policeonly", "sched", "police"):
            runs.append(point("policing", profile, mbit, video_mbit=mbit))

    for mbit in (0, 4, 8, 12):
        for profile in ("baseline", "sched", "full"):
            runs.append(point("flood", profile, mbit, flood_mbit=mbit))

    for delay in (5, 25, 50, 100):
        for profile in ("baseline", "full"):
            runs.append(point("delay", profile, delay, core={"delay": f"{delay}ms"}))

    for loss in (0, 0.5, 1, 2):
        for profile in ("baseline", "full"):
            runs.append(point("loss", profile, loss, core={"loss": loss}))

    for profile in ("baseline", "full"):
        runs.append(point("outage", profile, 3, outage_s=3, packets=True))

    for packets in (20, 50, 100, 300):
        runs.append(point("queue", "sched", packets,
                          overrides={"vnf3": {"QUEUE_PKTS": packets}}))

    # Vídeo a 6 Mbit/s: acima do garantido em dois dos três casos.
    for af, be in ((3, 6), (5, 4), (7, 2)):
        runs.append(point("weights", "sched", f"{af}/{be}", video_mbit=6,
                          overrides={"vnf3": {"AF_RATE": f"{af}mbit", "BE_RATE": f"{be}mbit"}}))

    # Sobrecarga: sem gargalo (10 Gbit/s) e sem atraso no núcleo, para medir só a cadeia.
    fast = {"vnf3": {"LINK_RATE": "10gbit", "EF_RATE": "1gbit",
                     "AF_RATE": "4gbit", "BE_RATE": "4gbit"}}
    for load, streams in (("sem carga", 0), ("com TCP", 1)):
        common = {"tcp_streams": streams, "video_mbit": 0, "be_probe": False,
                  "core": {"delay": "0ms"}}
        runs.append(point("overhead", "direto", load, chain="none", **common))
        runs.append(point("overhead", "baseline", load, overrides=fast, **common))
        runs.append(point("overhead", "full", load, overrides=fast, **common))
    return runs


def run_point(qos, spec, duration, packets_path):
    """Executa uma corrida e devolve {fluxo: métricas}."""
    if spec["chain"] == "default":
        qos.apply_profile(spec["profile"], spec["overrides"])
    qos.set_core(**spec["core"])
    for host in list(qos.config["clients"]) + list(qos.config["servers"]):
        qos[host].cmd("pkill udpgen; pkill -f 'iperf3 -c'; rm -f /tmp/udp-* /tmp/tcp-*")

    flows = {}
    if spec["tcp_streams"]:
        flows["bulk"] = TcpFlow(qos, "h_bulk", "srv_bulk", duration=duration + 2,
                                streams=spec["tcp_streams"])
        time.sleep(1.5)  # deixa o TCP encher a fila antes de medir
    if spec["flood_mbit"]:
        flows["flood"] = UdpFlow(qos, "h_x", "srv_bulk", port=FLOOD_PORT, size=VIDEO["size"],
                                 pps=spec["flood_mbit"] * 1e6 / VIDEO_PACKET_BITS,
                                 duration=duration)
    if spec["voip"]:
        flows["voip"] = UdpFlow(qos, "h_voip", "srv_voip", duration=duration,
                                packets=spec["packets"], **VOIP)
    if spec["video_mbit"]:
        flows["video"] = UdpFlow(qos, "h_video", "srv_video", port=VIDEO["port"],
                                 size=VIDEO["size"], duration=duration,
                                 pps=spec["video_mbit"] * 1e6 / VIDEO_PACKET_BITS)
    if spec["be_probe"]:
        flows["be_probe"] = UdpFlow(qos, "h_bulk", "srv_bulk", duration=duration, **BE_PROBE)

    if spec["outage_s"]:  # falha da ligação ao núcleo a meio da corrida
        time.sleep(duration / 2)
        qos.set_core(loss=100)
        time.sleep(spec["outage_s"])
        qos.set_core(**spec["core"])

    results = {name: flow.result() for name, flow in flows.items()}
    if spec["packets"] and "voip" in flows:
        flows["voip"].save_packets(packets_path)
    return results


def done_keys(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="") as handle:
        return {(r["experiment"], r["profile"], r["x"], r["rep"]) for r in csv.DictReader(handle)}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", choices=SETS, default="quick")
    parser.add_argument("--only", help="lista de cenários separados por vírgulas")
    parser.add_argument("--list", action="store_true", help="mostra as corridas e sai")
    args = parser.parse_args()

    settings = SETS[args.set]
    selected = [p for p in points() if not args.only or p["experiment"] in args.only.split(",")]
    total = len(selected) * settings["reps"]
    if args.list:
        for spec in selected:
            print(spec["experiment"], spec["profile"], spec["x"])
        print(f"{total} corridas, cerca de {total * (settings['duration'] + 9) // 60} min")
        return

    out_dir = os.path.join(ROOT, "results", args.set)
    os.makedirs(os.path.join(out_dir, "packets"), exist_ok=True)
    csv_path = os.path.join(out_dir, "runs.csv")
    done = done_keys(csv_path)
    new_file = not os.path.exists(csv_path)

    setLogLevel("warning")
    count, failed = 0, []
    with open(csv_path, "a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        # Uma rede por tipo de cadeia: primeiro a completa, depois a direta.
        for chain in ("default", "none"):
            todo = [(spec, rep) for spec in selected if spec["chain"] == chain
                    for rep in range(1, settings["reps"] + 1)
                    if (spec["experiment"], spec["profile"], str(spec["x"]), str(rep)) not in done]
            count += sum(1 for spec in selected if spec["chain"] == chain) \
                * settings["reps"] - len(todo)
            if not todo:
                continue
            config = load_config()
            if chain == "none":
                config = copy.deepcopy(config)
                config["chain"] = []
            qos = QosNet(config).build()
            try:
                qos.start("baseline" if chain == "default" else None)
                for spec, rep in todo:
                    count += 1
                    label = f"{spec['experiment']}/{spec['profile']}/x={spec['x']}/rep={rep}"
                    print(f"[{count}/{total}] {label}", flush=True)
                    packets_path = os.path.join(
                        out_dir, "packets",
                        f"{spec['experiment']}-{spec['profile']}-{spec['x']}-{rep}.csv")
                    try:
                        results = run_point(qos, spec, settings["duration"], packets_path)
                    except Exception as error:  # uma corrida falhada não pára a campanha
                        failed.append(label)
                        print(f"  FALHOU: {error}", flush=True)
                        continue
                    for flow, metrics in results.items():
                        writer.writerow({**metrics, "flow": flow, "rep": rep,
                                         "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                         "experiment": spec["experiment"],
                                         "profile": spec["profile"], "x": spec["x"],
                                         "duration_s": settings["duration"]})
                    handle.flush()
            finally:
                qos.stop()
    print(f"resultados em {csv_path}")
    if failed:  # não ficaram gravadas: basta voltar a correr a campanha
        print(f"{len(failed)} corridas falharam e ficam por repetir: " + ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
