#!/usr/bin/env python3
"""Gera o dashboard do Grafana (grafana/dashboards/qos.json).

O JSON do Grafana é longo e repetitivo; gerá-lo a partir desta lista de
painéis torna mais fácil ver e alterar o que cada gráfico mostra.

    python3 monitoring/make_dashboard.py
"""
import json
import os

PANELS = [
    # (título, unidade, expressão PromQL, legenda)
    ("Débito à saída da cadeia, por classe (VNF4 Monitor)", "bps",
     'rate(qosi_nft_bytes_total{vnf="vnf4"}[5s]) * 8', "{{name}}"),
    ("Ocupação das filas no gargalo (VNF3 Scheduler)", "short",
     'qosi_tc_qdisc_queue_packets{vnf="vnf3", kind="pfifo"}', "{{class}}"),
    ("Descartes nas filas do gargalo (VNF3 Scheduler)", "pps",
     'rate(qosi_tc_class_drops_total{vnf="vnf3", class=~"ef|af31|be|fifo"}[5s])', "{{class}}"),
    ("Descartes do policiador, por classe (VNF3 Policer)", "pps",
     'rate(qosi_tc_police_drops_total{vnf="vnf3"}[5s])', "{{class}}"),
    ("Firewall: pacotes aceites e bloqueados (VNF2)", "pps",
     'rate(qosi_nft_packets_total{vnf="vnf2"}[5s])', "{{name}}"),
    ("Classificador: pacotes marcados, por tipo (VNF1)", "pps",
     'rate(qosi_nft_packets_total{vnf="vnf1"}[5s])', "{{name}}"),
]


def panel(index, title, unit, expr, legend):
    return {
        "id": index + 1,
        "type": "timeseries",
        "title": title,
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 8, "w": 12, "x": 12 * (index % 2), "y": 8 * (index // 2)},
        "fieldConfig": {
            "defaults": {"unit": unit, "min": 0,
                         "custom": {"lineWidth": 2, "fillOpacity": 10, "showPoints": "never"}},
            "overrides": [],
        },
        "options": {"legend": {"displayMode": "list", "placement": "bottom"},
                    "tooltip": {"mode": "multi"}},
        "targets": [{"refId": "A", "expr": expr, "legendFormat": legend,
                     "datasource": {"type": "prometheus", "uid": "prometheus"}}],
    }


def main():
    dashboard = {
        "uid": "qosi-tp3",
        "title": "QoSI TP3: cadeia de VNFs",
        "tags": ["qosi"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "1s",
        "time": {"from": "now-5m", "to": "now"},
        "timepicker": {"refresh_intervals": ["1s", "5s", "10s", "30s"]},
        "panels": [panel(i, *spec) for i, spec in enumerate(PANELS)],
    }
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "grafana", "dashboards", "qos.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(dashboard, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(path)


if __name__ == "__main__":
    main()
