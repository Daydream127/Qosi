# Imagem da VNF "monitor". Construir com o contexto em vnfs/:
#   docker build -f vnfs/monitor/Dockerfile -t qosi/monitor vnfs
FROM qosi/base

COPY common/exporter.py /vnf/exporter.py
COPY monitor/start /vnf/start
RUN chmod +x /vnf/start /vnf/exporter.py
