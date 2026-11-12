#!/usr/bin/env bash
# Arranca o Prometheus e o Grafana em contentores.
#   Prometheus: http://localhost:9090
#   Grafana:    http://localhost:3000  (dashboard "QoSI TP3", sem login)
#
# Usam a rede do anfitrião para chegarem aos exportadores das VNFs, que estão
# na rede de gestão (a bridge por omissão do Docker).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p targets
[ -f targets/vnfs.json ] || echo "[]" > targets/vnfs.json

docker rm -f qosi-prometheus qosi-grafana >/dev/null 2>&1 || true

docker run -d --name qosi-prometheus --network host --restart unless-stopped \
  -v "$PWD/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  -v "$PWD/targets:/etc/prometheus/targets:ro" \
  prom/prometheus:v2.53.0 \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.retention.time=2d >/dev/null

docker run -d --name qosi-grafana --network host --restart unless-stopped \
  -e GF_AUTH_ANONYMOUS_ENABLED=true \
  -e GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer \
  -e GF_AUTH_DISABLE_LOGIN_FORM=true \
  -e GF_DASHBOARDS_MIN_REFRESH_INTERVAL=1s \
  -e GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/var/lib/grafana/dashboards/qos.json \
  -v "$PWD/grafana/provisioning:/etc/grafana/provisioning:ro" \
  -v "$PWD/grafana/dashboards:/var/lib/grafana/dashboards:ro" \
  grafana/grafana-oss:11.1.0 >/dev/null

echo "Prometheus: http://localhost:9090"
echo "Grafana:    http://localhost:3000"
