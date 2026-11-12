#!/usr/bin/env bash
# Para e remove os contentores do Prometheus e do Grafana.
docker rm -f qosi-prometheus qosi-grafana >/dev/null 2>&1 || true
echo "monitorização parada"
