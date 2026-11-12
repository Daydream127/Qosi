# Imagem da VNF "classifier". Construir com o contexto em vnfs/:
#   docker build -f vnfs/classifier/Dockerfile -t qosi/classifier vnfs
FROM qosi/base

COPY common/exporter.py /vnf/exporter.py
COPY classifier/start /vnf/start
RUN chmod +x /vnf/start /vnf/exporter.py
