#!/usr/bin/env python3
"""Gerador e recetor de tráfego UDP com medição ativa de QoS.

Cada pacote leva um número de sequência e uma estampilha temporal de envio, o
que permite ao recetor calcular as métricas one-way:

  - OWD/IPTD: atraso num sentido (receção - envio). É válido porque todos os
    nós emulados partilham o relógio da máquina. Usa-se o relógio monotónico
    (CLOCK_MONOTONIC), que é comum a todos os contentores e, ao contrário do
    relógio de parede, não dá saltos quando o sistema acerta a hora.
  - IPDV: variação do atraso entre pacotes consecutivos (RFC 3393) e o jitter
    suavizado do RFC 3550.
  - IPLR: razão de perdas, a partir dos números de sequência em falta.

Exemplos:
  udpgen recv --port 5004 --duration 35 --json /tmp/voip.json
  udpgen send --dst 10.0.2.11 --port 5004 --pps 50 --size 172 --duration 30
"""
import argparse
import json
import math
import signal
import socket
import struct
import sys
import time

HEADER = struct.Struct("!IQ")  # n.º de sequência, instante de envio (ns)
FIN_SEQ = 0xFFFFFFFF  # pacote de fim: o campo de tempo leva o total enviado
IP_UDP_OVERHEAD = 28


def percentile(sorted_values, q):
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, max(0, math.ceil(q * len(sorted_values)) - 1))
    return sorted_values[index]


def send(args):
    payload_size = max(args.size, HEADER.size)
    padding = b"\0" * (payload_size - HEADER.size)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dst = (args.dst, args.port)
    interval = 1.0 / args.pps
    total = int(args.pps * args.duration)

    start = time.perf_counter()
    for seq in range(total):
        target = start + seq * interval
        # Dorme quase até ao instante certo e afina com espera ativa.
        remaining = target - time.perf_counter()
        if remaining > 0.001:
            time.sleep(remaining - 0.0005)
        while time.perf_counter() < target:
            pass
        sock.sendto(HEADER.pack(seq, time.monotonic_ns()) + padding, dst)

    elapsed = time.perf_counter() - start
    for _ in range(5):  # o fim é repetido porque também se pode perder
        sock.sendto(HEADER.pack(FIN_SEQ, total), dst)
        time.sleep(0.02)

    print(json.dumps({"sent": total, "duration_s": round(elapsed, 3),
                      "pps": args.pps, "payload_bytes": payload_size}))


def receive(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    sock.bind(("0.0.0.0", args.port))
    sock.settimeout(0.2)

    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))

    samples = []  # (seq, atraso em ms)
    sent_at = []  # instante de envio de cada amostra (ns), para o CSV por pacote
    max_gap_ns = 0  # maior intervalo entre chegadas: denuncia pausas na medição
    sent_total = None
    received_bytes = 0
    first_rx = last_rx = None
    deadline = time.monotonic() + args.duration
    fin_deadline = None

    while not stop["flag"] and time.monotonic() < deadline:
        if fin_deadline is not None and time.monotonic() > fin_deadline:
            break
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            continue
        now_ns = time.monotonic_ns()
        if len(data) < HEADER.size:
            continue
        seq, value = HEADER.unpack_from(data)
        if seq == FIN_SEQ:
            sent_total = value
            if fin_deadline is None:  # espera um pouco por pacotes atrasados
                fin_deadline = time.monotonic() + 0.3
            continue
        samples.append((seq, (now_ns - value) / 1e6))
        sent_at.append(value)
        if first_rx is None:
            # O primeiro pacote só marca o início do intervalo de medição do
            # débito: N pacotes ocupam N-1 intervalos entre chegadas.
            first_rx = now_ns
        else:
            received_bytes += len(data) + IP_UDP_OVERHEAD
            max_gap_ns = max(max_gap_ns, now_ns - last_rx)
        last_rx = now_ns

    summary = summarize(samples, sent_total, received_bytes, first_rx, last_rx)
    summary["rx_gap_ms_max"] = round(max_gap_ns / 1e6, 3)
    text = json.dumps(summary)
    if args.json:
        with open(args.json, "w") as handle:
            handle.write(text + "\n")
    if args.csv:
        with open(args.csv, "w") as handle:
            # t_ms: instante de envio, contado a partir do primeiro pacote recebido.
            handle.write("seq,t_ms,owd_ms\n")
            handle.writelines(f"{seq},{(sent - sent_at[0]) / 1e6:.3f},{owd:.3f}\n"
                              for (seq, owd), sent in zip(samples, sent_at))
    print(text)


def summarize(samples, sent_total, received_bytes, first_rx, last_rx):
    received = len({seq for seq, _ in samples})
    if sent_total is None:  # sem pacote de fim: estima pelo maior n.º de sequência
        sent_total = max((seq for seq, _ in samples), default=-1) + 1
    lost = max(0, sent_total - received)

    delays = [owd for _, owd in samples]
    ordered = sorted(delays)
    ipdv = [abs(b - a) for a, b in zip(delays, delays[1:])]
    jitter = 0.0
    for variation in ipdv:  # estimador do RFC 3550
        jitter += (variation - jitter) / 16.0

    duration = (last_rx - first_rx) / 1e9 if samples and last_rx > first_rx else 0.0
    return {
        "sent": sent_total,
        "received": received,
        "lost": lost,
        "loss_ratio": round(lost / sent_total, 6) if sent_total else None,
        "owd_ms_mean": round(sum(delays) / len(delays), 3) if delays else None,
        "owd_ms_min": round(ordered[0], 3) if delays else None,
        "owd_ms_p50": round(percentile(ordered, 0.50), 3) if delays else None,
        "owd_ms_p95": round(percentile(ordered, 0.95), 3) if delays else None,
        "owd_ms_p99": round(percentile(ordered, 0.99), 3) if delays else None,
        "owd_ms_max": round(ordered[-1], 3) if delays else None,
        "ipdv_ms_mean": round(sum(ipdv) / len(ipdv), 3) if ipdv else None,
        "ipdv_ms_p95": round(percentile(sorted(ipdv), 0.95), 3) if ipdv else None,
        "jitter_rfc3550_ms": round(jitter, 3) if ipdv else None,
        "throughput_kbps": round(received_bytes * 8 / duration / 1000, 1) if duration else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    tx = sub.add_parser("send", help="envia um fluxo UDP de débito constante")
    tx.add_argument("--dst", required=True)
    tx.add_argument("--port", type=int, required=True)
    tx.add_argument("--pps", type=float, required=True, help="pacotes por segundo")
    tx.add_argument("--size", type=int, default=172, help="tamanho do payload UDP em bytes")
    tx.add_argument("--duration", type=float, default=10.0, help="segundos")
    tx.set_defaults(func=send)

    rx = sub.add_parser("recv", help="recebe um fluxo e calcula as métricas")
    rx.add_argument("--port", type=int, required=True)
    rx.add_argument("--duration", type=float, default=60.0, help="tempo máximo de escuta")
    rx.add_argument("--json", help="ficheiro para o resumo em JSON")
    rx.add_argument("--csv", help="ficheiro para as amostras por pacote")
    rx.set_defaults(func=receive)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
