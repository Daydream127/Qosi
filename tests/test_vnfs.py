#!/usr/bin/env python3
"""Testes das VNFs, uma de cada vez, com tráfego controlado.

Levanta a topologia uma única vez e, para cada teste, ativa apenas a VNF em
causa (as outras ficam em modo de passagem). Correr dentro da VM:

    sudo /opt/containernet/venv/bin/python3 tests/test_vnfs.py

Termina com código 0 se todas as verificações passarem.
"""
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "topology"))

from qosnet import EXPORTER_PORT, QosNet  # noqa: E402
from flows import VIDEO, VOIP, TcpFlow, UdpFlow, tcp_with_udp, udp_window_end  # noqa: E402
from mininet.log import setLogLevel  # noqa: E402

# Combinações de VNFs ativas usadas nos testes.
ALL_OFF = {"vnf1": {"ENABLED": 0}, "vnf2": {"ENABLED": 0},
           "vnf3": {"SCHEDULING": 0, "POLICING": 0}}
ONLY_CLASSIFIER = {"vnf2": {"ENABLED": 0}, "vnf3": {"SCHEDULING": 0, "POLICING": 0}}
ONLY_FIREWALL = {"vnf1": {"ENABLED": 0}, "vnf3": {"SCHEDULING": 0, "POLICING": 0}}
CLASSIFIER_POLICER = {"vnf2": {"ENABLED": 0}, "vnf3": {"SCHEDULING": 0, "POLICING": 1}}
CLASSIFIER_SCHEDULER = {"vnf2": {"ENABLED": 0}, "vnf3": {"SCHEDULING": 1, "POLICING": 0}}

results = []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(f"  [{'OK' if condition else 'FALHOU'}] {name}" + (f"  ({detail})" if detail else ""))


def section(title):
    print(f"\n=== {title}")


def captured_tos(qos, capture_filter, send):
    """Valor do campo ToS dos pacotes que chegam à VNF2, vindos da VNF1."""
    vnf2 = qos["vnf2"]
    vnf2.cmd(f"timeout 6 tcpdump -i vnf2-in -nn -v -c 3 '{capture_filter}' "
             ">/tmp/capture.txt 2>/dev/null &")
    time.sleep(0.5)
    send()
    time.sleep(3)
    found = re.findall(r"tos (0x[0-9a-f]+)", vnf2.cmd("cat /tmp/capture.txt"))
    return found[0] if found else None


def test_chain(qos):
    section("Cadeia em modo de passagem: conectividade e ordem dos saltos")
    qos.configure(ALL_OFF)
    h_voip = qos["h_voip"]
    ping = h_voip.cmd(f"ping -c 3 -i 0.2 -W 1 {qos.ip('srv_voip')}")
    check("ping h_voip -> srv_voip sem perdas", " 0% packet loss" in ping)
    hops = re.findall(r"^\s*\d+\s+(\d+\.\d+\.\d+\.\d+)",
                      h_voip.cmd(f"traceroute -n -q 1 -w 1 {qos.ip('srv_voip')}"), re.M)
    expected = ["10.0.1.1", "10.0.10.2", "10.0.11.2", "10.0.12.2", "10.0.13.2",
                qos.ip("srv_voip")]
    check("traceroute passa por vnf1, vnf2, vnf3, vnf4 e r1", hops == expected, " > ".join(hops))


def test_classifier(qos):
    section("VNF1 Classificador: marcação DSCP")
    dst = qos.ip("srv_voip")
    voip = lambda: qos["h_voip"].cmd(  # noqa: E731
        f"udpgen send --dst {dst} --port {VOIP['port']} --pps 20 --duration 1 >/dev/null &")
    video = lambda: qos["h_voip"].cmd(  # noqa: E731
        f"udpgen send --dst {dst} --port {VIDEO['port']} --pps 20 --duration 1 >/dev/null &")
    # Um cliente que marca o seu próprio tráfego como EF não deve ser acreditado.
    cheater = lambda: qos["h_voip"].cmd(  # noqa: E731
        f"ping -c 5 -i 0.2 -Q 0xb8 {dst} >/dev/null &")

    qos.configure(ALL_OFF)
    tos = captured_tos(qos, f"udp dst port {VOIP['port']}", voip)
    check("classificador desligado: VoIP segue sem marcação", tos == "0x0", f"tos {tos}")

    qos.configure(ONLY_CLASSIFIER)
    tos = captured_tos(qos, f"udp dst port {VOIP['port']}", voip)
    check("VoIP (UDP 5004) marcado como EF", tos == "0xb8", f"tos {tos}")
    tos = captured_tos(qos, f"udp dst port {VIDEO['port']}", video)
    check("vídeo (UDP 5006) marcado como AF31", tos == "0x68", f"tos {tos}")
    tos = captured_tos(qos, "icmp[icmptype] == icmp-echo", cheater)
    check("tráfego pré-marcado pelo cliente é remarcado como BE", tos == "0x0", f"tos {tos}")


def test_firewall(qos):
    section("VNF2 Firewall: controlo de acesso")
    qos.configure(ONLY_FIREWALL)
    dst = qos.ip("srv_voip")

    allowed = UdpFlow(qos, "h_voip", "srv_voip", duration=2, **VOIP).result()
    check("cliente autorizado: VoIP passa", allowed and allowed["loss_ratio"] < 0.01,
          f"{allowed['received']}/{allowed['sent']} pacotes")
    tcp = TcpFlow(qos, "h_bulk", "srv_bulk", duration=2).result()
    check("cliente autorizado: TCP 5201 passa", tcp["throughput_kbps"] > 1000,
          f"{tcp['throughput_kbps']} kbit/s")

    ping = qos["h_x"].cmd(f"ping -c 2 -W 1 {dst}")
    check("h_x: ping bloqueado", "100% packet loss" in ping)
    blocked = UdpFlow(qos, "h_x", "srv_voip", duration=2, **VOIP).result()
    check("h_x: UDP bloqueado", blocked and blocked["received"] == 0,
          f"{blocked['received']} pacotes recebidos")
    wrong_port = UdpFlow(qos, "h_voip", "srv_voip", port=9999, pps=50, size=172,
                         duration=2).result()
    check("porta não autorizada bloqueada", wrong_port and wrong_port["received"] == 0,
          f"{wrong_port['received']} pacotes recebidos")
    dropped = re.search(r"counter dropped \{\s*packets (\d+)",
                        qos["vnf2"].cmd("nft list counter ip firewall dropped"))
    check("contador de pacotes descartados incrementa", dropped and int(dropped.group(1)) > 100,
          f"{dropped.group(1) if dropped else '?'} pacotes")


def test_policer(qos):
    section("VNF3 Policer: token bucket por classe (EF contratado a 200 kbit/s)")
    qos.configure(CLASSIFIER_POLICER)
    conforming = UdpFlow(qos, "h_voip", "srv_voip", duration=5, **VOIP).result()
    check("VoIP dentro do perfil (80 kbit/s) não sofre perdas",
          conforming["loss_ratio"] < 0.01, f"perdas {conforming['loss_ratio']:.2%}")
    excess = UdpFlow(qos, "h_voip", "srv_voip", port=VOIP["port"], pps=250, size=172,
                     duration=5).result()
    check("VoIP a 400 kbit/s é limitado a cerca de 200 kbit/s",
          170 <= excess["throughput_kbps"] <= 230,
          f"{excess['throughput_kbps']} kbit/s, perdas {excess['loss_ratio']:.0%}")


def congestion(qos, duration=10):
    """VoIP e vídeo em concorrência com quatro fluxos TCP no gargalo de 10 Mbit/s."""
    bulk = tcp_with_udp(qos, "h_bulk", "srv_bulk", duration, streams=4)
    voip = UdpFlow(qos, "h_voip", "srv_voip", duration=duration, **VOIP)
    video = UdpFlow(qos, "h_video", "srv_video", duration=duration, **VIDEO)
    # O débito TCP só é medido enquanto o VoIP e o vídeo estão presentes.
    bulk.start_window()
    bulk.end_window(at=udp_window_end([voip, video]))
    return voip.result(), video.result(), bulk.result()


def test_scheduler(qos):
    section("VNF3 Scheduler: congestionamento com e sem agendamento")
    qos.configure(ALL_OFF)
    voip0, video0, bulk0 = congestion(qos)
    print(f"  sem QoS:  VoIP OWD p95 {voip0['owd_ms_p95']} ms, perdas {voip0['loss_ratio']:.2%} | "
          f"vídeo perdas {video0['loss_ratio']:.2%} | TCP {bulk0['throughput_kbps']} kbit/s")
    qos.configure(CLASSIFIER_SCHEDULER)
    voip1, video1, bulk1 = congestion(qos)
    print(f"  com HTB:  VoIP OWD p95 {voip1['owd_ms_p95']} ms, perdas {voip1['loss_ratio']:.2%} | "
          f"vídeo perdas {video1['loss_ratio']:.2%} | TCP {bulk1['throughput_kbps']} kbit/s")

    check("sem QoS, o VoIP sofre com a fila partilhada (OWD p95 > 50 ms)",
          voip0["owd_ms_p95"] > 50)
    check("com agendamento, VoIP com OWD p95 < 20 ms", voip1["owd_ms_p95"] < 20)
    check("com agendamento, VoIP sem perdas", voip1["loss_ratio"] < 0.001)
    check("com agendamento, vídeo com perdas < 1%", video1["loss_ratio"] < 0.01)
    check("o TCP continua a usar a capacidade restante (> 3 Mbit/s)",
          bulk1["throughput_kbps"] > 3000)


def test_monitor(qos):
    section("VNF4 Monitor: contadores por classe e exportador de métricas")
    qos.configure(ONLY_CLASSIFIER)

    def ef_packets():
        text = qos["vnf4"].cmd("nft list counter ip probe class_ef")
        return int(re.search(r"packets (\d+)", text).group(1))

    before = ef_packets()
    flow = UdpFlow(qos, "h_voip", "srv_voip", duration=2, **VOIP).result()
    counted = ef_packets() - before
    check("contador EF acompanha os pacotes VoIP recebidos",
          abs(counted - flow["received"]) <= 6, f"{counted} contados, {flow['received']} recebidos")

    for name in ("vnf1", "vnf2", "vnf3", "vnf4"):
        url = f"http://{qos.management_ip(name)}:{EXPORTER_PORT}/metrics"
        try:
            body = urllib.request.urlopen(url, timeout=3).read().decode()
        except OSError as error:
            body = ""
            print(f"    {name}: {error}")
        check(f"{name} exporta métricas na rede de gestão", "qosi_iface_rx_bytes_total" in body,
              f"{len(body.splitlines())} linhas")
        if name == "vnf4":
            check("métricas do monitor incluem os contadores por classe",
                  'qosi_nft_packets_total{name="class_ef"' in body)
        if name == "vnf3":
            check("métricas da VNF3 incluem as filas do tc", "qosi_tc_class_drops_total" in body)


def main():
    setLogLevel("warning")
    qos = QosNet().build()
    try:
        qos.start("baseline")
        for test in (test_chain, test_classifier, test_firewall, test_policer,
                     test_scheduler, test_monitor):
            test(qos)
    finally:
        qos.stop()

    passed = sum(results)
    print(f"\n{passed}/{len(results)} verificações passaram")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
