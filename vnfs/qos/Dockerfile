# Imagem da VNF "qos". Construir com o contexto em vnfs/:
#   docker build -f vnfs/qos/Dockerfile -t qosi/qos vnfs
FROM qosi/base

COPY common/exporter.py /vnf/exporter.py
COPY qos/start /vnf/start
RUN chmod +x /vnf/start /vnf/exporter.py
