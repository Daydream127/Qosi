#!/usr/bin/env python3
"""Exportador de métricas de uma VNF no formato do Prometheus.

Corre dentro de cada VNF e expõe, na interface de gestão (porta 9100):
  - os contadores com nome do nftables (pacotes e bytes por regra/classe);
  - as estatísticas das classes e filas do tc (enviados, descartados, fila);
  - as estatísticas dos policiadores do tc à entrada;
  - os contadores das interfaces de rede.

Só usa a biblioteca padrão do Python, para a imagem das VNFs ficar pequena.
"""
import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

VNF = os.environ.get("VNF_NAME", "vnf")
PORT = int(os.environ.get("EXPORTER_PORT", "9100"))
# Endereço onde o exportador escuta: o da interface de gestão, para as métricas
# não ficarem acessíveis a partir da rede de dados (clientes e servidores).
ADDRESS = os.environ.get("EXPORTER_ADDR", "0.0.0.0")
CLASS_NAMES_FILE = "/vnf/tc_class_names"  # linhas "1:10 ef", escritas pela VNF de QoS


CLASS_RE = re.compile(r"class htb (\S+) .*\n Sent (\d+) bytes (\d+) pkt "
                      r"\(dropped (\d+), overlimits (\d+)")
PREF_RE = re.compile(r"^filter .*\bpref (\d+) ")
POLICE_STATS_RE = re.compile(r"Sent (\d+) bytes (\d+) pkts? \(dropped (\d+), overlimits (\d+)")


def run_text(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def run_json(cmd):
    try:
        out = run_text(cmd)
        return json.loads(out) if out.strip() else []
    except ValueError:
        return []


def data_interfaces():
    return sorted(d for d in os.listdir("/sys/class/net") if d not in ("lo", "eth0"))


def class_names():
    names = {}
    try:
        with open(CLASS_NAMES_FILE) as handle:
            for line in handle:
                parts = line.split()
                if len(parts) == 2:
                    names[parts[0]] = parts[1]
    except OSError:
        pass
    return names


def metric(lines, name, labels, value):
    label_text = ",".join(f'{key}="{val}"' for key, val in sorted(labels.items()))
    lines.append(f"qosi_{name}{{{label_text}}} {value}")


def collect():
    lines = []

    ruleset = run_json(["nft", "-j", "list", "counters"])
    for item in ruleset.get("nftables", []) if isinstance(ruleset, dict) else []:
        counter = item.get("counter")
        if counter:
            labels = {"vnf": VNF, "table": counter["table"], "name": counter["name"]}
            metric(lines, "nft_packets_total", labels, counter["packets"])
            metric(lines, "nft_bytes_total", labels, counter["bytes"])

    names = class_names()
    for dev in data_interfaces():
        # O tc 5.15 não devolve JSON válido para classes HTB nem para filtros
        # u32, por isso esses dois são lidos a partir do formato de texto.
        for handle, sent_bytes, packets, drops, overlimits in CLASS_RE.findall(
                run_text(["tc", "-s", "class", "show", "dev", dev])):
            labels = {"vnf": VNF, "dev": dev, "classid": handle,
                      "class": names.get(handle, handle)}
            metric(lines, "tc_class_bytes_total", labels, sent_bytes)
            metric(lines, "tc_class_packets_total", labels, packets)
            metric(lines, "tc_class_drops_total", labels, drops)
            metric(lines, "tc_class_overlimits_total", labels, overlimits)

        pref = ""
        for line in run_text(["tc", "-s", "filter", "show", "dev", dev, "ingress"]).splitlines():
            found = PREF_RE.search(line)
            if found:
                pref = found.group(1)
            found = POLICE_STATS_RE.search(line)
            if found:
                labels = {"vnf": VNF, "dev": dev, "pref": pref,
                          "class": names.get(f"police:{pref}", pref)}
                metric(lines, "tc_police_bytes_total", labels, found.group(1))
                metric(lines, "tc_police_packets_total", labels, found.group(2))
                metric(lines, "tc_police_drops_total", labels, found.group(3))

        for qdisc in run_json(["tc", "-s", "-j", "qdisc", "show", "dev", dev]):
            stats = qdisc.get("stats", qdisc)
            parent = qdisc.get("parent", "root" if qdisc.get("root") else "")
            labels = {"vnf": VNF, "dev": dev, "kind": qdisc.get("kind", ""),
                      "handle": qdisc.get("handle", ""), "parent": parent,
                      "class": names.get(parent, parent)}
            metric(lines, "tc_qdisc_drops_total", labels, stats.get("drops", 0))
            metric(lines, "tc_qdisc_backlog_bytes", labels, stats.get("backlog", 0))
            metric(lines, "tc_qdisc_queue_packets", labels, stats.get("qlen", 0))

        base = f"/sys/class/net/{dev}/statistics"
        for stat in ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets",
                     "rx_dropped", "tx_dropped"):
            try:
                with open(f"{base}/{stat}") as handle:
                    metric(lines, f"iface_{stat}_total", {"vnf": VNF, "dev": dev},
                           handle.read().strip())
            except OSError:
                pass

    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = collect().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    HTTPServer((ADDRESS, PORT), Handler).serve_forever()
