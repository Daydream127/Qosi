# Imagem da VNF "firewall". Construir com o contexto em vnfs/:
#   docker build -f vnfs/firewall/Dockerfile -t qosi/firewall vnfs
FROM qosi/base

COPY common/exporter.py /vnf/exporter.py
COPY firewall/start /vnf/start
RUN chmod +x /vnf/start /vnf/exporter.py
