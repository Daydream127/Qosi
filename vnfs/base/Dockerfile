# Imagem base de todos os nós da topologia (clientes, servidores e VNFs).
# O Containernet precisa de bash, iproute2 e net-tools dentro do contentor.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      iproute2 net-tools iputils-ping traceroute tcpdump ethtool \
      nftables iperf3 python3 \
 && rm -rf /var/lib/apt/lists/*

# Sem isto, o bash mistura sequências de escape no output que o Mininet lê,
# o que gera falsos erros ("Error setting h1-eth0 up").
RUN echo "set enable-bracketed-paste off" >> /etc/inputrc

CMD ["/bin/bash"]
