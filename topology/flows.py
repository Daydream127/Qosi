"""Geração de tráfego sobre a topologia: fluxos UDP medidos e fluxos TCP.

Os fluxos arrancam em segundo plano dentro dos contentores, para poderem
correr vários ao mesmo tempo; os resultados são lidos no fim com result().
"""
import itertools
import json
import subprocess
import time

_ids = itertools.count(1)

# Perfis de tráfego da proposta (payload UDP; os 28 bytes de IP+UDP somam-se).
VOIP = {"port": 5004, "pps": 50, "size": 172}      # 200 B por pacote, 80 kbit/s
VIDEO = {"port": 5006, "pps": 400, "size": 1222}   # 1250 B por pacote, 4 Mbit/s
BE_PROBE = {"port": 5008, "pps": 20, "size": 172}  # sonda na classe best effort
BULK_PORT = 5201
FLOOD_PORT = 5009                                  # tráfego não autorizado de h_x


class UdpFlow:
    """Fluxo UDP medido pelo udpgen no destino.

    O débito é constante; com burst=N, os pacotes saem em rajadas de N.
    """

    def __init__(self, qos, client, server, port, pps, size, duration, packets=False, burst=1):
        self.qos, self.duration = qos, duration
        self.server = qos[server]
        self.rx_file = f"/tmp/udp-rx-{next(_ids)}.json"
        self.tx_file = self.rx_file.replace("rx", "tx")
        # Com packets=True, o recetor guarda também uma linha por pacote.
        self.packets_file = self.rx_file.replace(".json", ".csv") if packets else None
        csv_option = f"--csv {self.packets_file} " if packets else ""
        self.server.cmd(f"udpgen recv --port {port} --duration {duration + 3} {csv_option}"
                        f"--json {self.rx_file} >/dev/null 2>&1 &")
        time.sleep(0.3)  # dá tempo ao recetor para abrir a porta
        self.client = qos[client]
        self.client.cmd(f"udpgen send --dst {qos.ip(server)} --port {port} --pps {pps} "
                        f"--size {size} --duration {duration} --burst {burst} "
                        f">{self.tx_file} 2>&1 &")
        self.started = time.monotonic()

    def result(self):
        """Espera pelo fim do fluxo e devolve as métricas medidas no recetor."""
        wait = self.started + self.duration + 3.5 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        received = _read_json(self.server, self.rx_file)
        sent = _read_json(self.client, self.tx_file)
        if sent and received:  # o emissor sabe ao certo quantos pacotes enviou
            received["sent"] = sent["sent"]
            received["lost"] = sent["sent"] - received["received"]
            received["loss_ratio"] = round(received["lost"] / sent["sent"], 6)
        return received or {}

    def save_packets(self, path):
        """Copia para fora do contentor as amostras por pacote (seq, t_ms, owd_ms)."""
        subprocess.run(["docker", "cp", f"mn.{self.server.name}:{self.packets_file}", path],
                       check=False, capture_output=True)


class TcpFlow:
    """Transferência TCP sem limite de débito (dados em massa), com o iperf3."""

    def __init__(self, qos, client, server, duration, streams=1, port=BULK_PORT):
        self.duration = duration
        self.client = qos[client]
        self.file = f"/tmp/tcp-{next(_ids)}.json"
        qos[server].cmd(f"pgrep -f 'iperf3 -s -p {port}' >/dev/null || iperf3 -s -p {port} -D")
        time.sleep(0.3)
        self.client.cmd(f"iperf3 -c {qos.ip(server)} -p {port} -t {duration} -P {streams} "
                        f"-J >{self.file} 2>&1 &")
        self.started = time.monotonic()

    def result(self):
        wait = self.started + self.duration + 2.5 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        # O iperf3 só escreve o resultado ao terminar e, a débitos muito altos ou
        # depois de uma falha da ligação, pode demorar mais uns segundos a fechar.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and \
                "RUNNING" in self.client.cmd("pgrep -x iperf3 >/dev/null && echo RUNNING"):
            time.sleep(0.5)
        data = _read_json(self.client, self.file) or {}
        end = data.get("end", {})
        received = end.get("sum_received", {})
        return {
            "throughput_kbps": round(received.get("bits_per_second", 0) / 1000, 1),
            "retransmits": end.get("sum_sent", {}).get("retransmits"),
            "error": data.get("error"),
        }


def _read_json(node, path):
    text = node.cmd(f"cat {path} 2>/dev/null").strip()
    try:
        return json.loads(text[text.index("{"):])
    except ValueError:
        return None
