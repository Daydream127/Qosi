"""Geração de tráfego sobre a topologia: fluxos UDP medidos e fluxos TCP.

Os fluxos arrancam em segundo plano dentro dos contentores, para poderem
correr vários ao mesmo tempo; os resultados são lidos no fim com result().
"""
import itertools
import json
import re
import subprocess
import time

_ids = itertools.count(1)

# Perfis de tráfego da proposta (payload UDP; os 28 bytes de IP+UDP somam-se).
VOIP = {"port": 5004, "pps": 50, "size": 172}      # 200 B por pacote, 80 kbit/s
VIDEO = {"port": 5006, "pps": 400, "size": 1222}   # 1250 B por pacote, 4 Mbit/s
BE_PROBE = {"port": 5008, "pps": 20, "size": 172}  # sonda na classe best effort
BULK_PORT = 5201
FLOOD_PORT = 5009                                  # tráfego não autorizado de h_x
TCP_HEAD_START = 1.5                               # avanço do TCP sobre os fluxos UDP (s)


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
    """Transferência TCP sem limite de débito (dados em massa), com o iperf3.

    O débito pode ser medido de duas formas. Por omissão é o que o iperf3
    reporta para toda a duração do fluxo. Com start_window() e end_window()
    mede-se só um intervalo, a partir dos bytes já confirmados pelo recetor
    (bytes_acked, lidos no cliente com o comando ss). É o que se usa quando o
    TCP corre ao lado de fluxos UDP: arranca antes deles, para encher a fila, e
    esse arranque sem concorrência não deve contar para a medição.
    """

    def __init__(self, qos, client, server, duration, streams=1, port=BULK_PORT):
        self.duration = duration
        self.port = port
        self.client = qos[client]
        self.file = f"/tmp/tcp-{next(_ids)}.json"
        self._mark = None         # (instante, bytes confirmados) no início da janela
        self.window_kbps = None   # débito medido na janela, se houver
        qos[server].cmd(f"pgrep -f 'iperf3 -s -p {port}' >/dev/null || iperf3 -s -p {port} -D")
        time.sleep(0.3)
        self.client.cmd(f"iperf3 -c {qos.ip(server)} -p {port} -t {duration} -P {streams} "
                        f"-J >{self.file} 2>&1 &")
        self.started = time.monotonic()

    def _sample(self):
        """(instante, bytes confirmados pelo recetor, somados sobre as ligações).

        Só contam as ligações abertas (established): as de uma corrida anterior
        que ainda estejam a fechar ficam de fora.
        """
        before = time.monotonic()
        text = self.client.cmd(f"ss -tin state established 'dport = :{self.port}'")
        acked = sum(int(value) for value in re.findall(r"bytes_acked:(\d+)", text))
        return (before + time.monotonic()) / 2, acked

    def start_window(self):
        """Início do intervalo de medição (chamar depois de arrancar os fluxos UDP)."""
        self._mark = self._sample()

    def end_window(self, at=None):
        """Fim do intervalo de medição; com `at`, espera primeiro por esse instante."""
        if at is not None and at > time.monotonic():
            time.sleep(at - time.monotonic())
        now, acked = self._sample()
        started, before = self._mark
        self.window_kbps = round((acked - before) * 8 / (now - started) / 1000, 1)

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
        whole_flow = round(received.get("bits_per_second", 0) / 1000, 1)
        return {
            "throughput_kbps": whole_flow if self.window_kbps is None else self.window_kbps,
            "retransmits": end.get("sum_sent", {}).get("retransmits"),
            "error": data.get("error"),
        }


def tcp_with_udp(qos, client, server, duration, streams):
    """Arranca o TCP que acompanha fluxos UDP de `duration` segundos.

    O TCP arranca TCP_HEAD_START segundos antes, para a fila já estar cheia
    quando os fluxos UDP começam, e só termina depois deles. Os fluxos UDP
    devem ser criados logo a seguir; depois, start_window() e
    end_window(at=udp_window_end(fluxos)) delimitam a medição do TCP.
    """
    flow = TcpFlow(qos, client, server, duration=duration + 3, streams=streams)
    time.sleep(TCP_HEAD_START)
    return flow


def udp_window_end(udp_flows):
    """Instante em que deve acabar a medição do TCP: meio segundo antes de o
    primeiro fluxo UDP terminar, para todo o tráfego UDP estar ainda presente."""
    return min(flow.started + flow.duration for flow in udp_flows) - 0.5


def stop_traffic(qos, hosts, tcp_client="h_bulk", timeout=30):
    """Pára os geradores de tráfego e espera que as ligações TCP antigas fechem.

    Quando o TCP fica sem débito, o iperf3 termina com dados por enviar e o
    núcleo continua a retransmiti-los depois de o processo sair. Sem esta
    espera, essas ligações ainda estariam ativas na corrida seguinte. Devolve
    o tempo de espera, em segundos.
    """
    for host in hosts:
        qos[host].cmd("pkill udpgen; pkill -9 iperf3; rm -f /tmp/udp-* /tmp/tcp-*")
    started = time.monotonic()
    # "big" exclui as entradas em TIME-WAIT, que já não transportam dados.
    while time.monotonic() - started < timeout and \
            qos[tcp_client].cmd(f"ss -Htn state big 'dport = :{BULK_PORT}'").strip():
        time.sleep(0.5)
    return round(time.monotonic() - started, 1)


def _read_json(node, path):
    text = node.cmd(f"cat {path} 2>/dev/null").strip()
    try:
        return json.loads(text[text.index("{"):])
    except ValueError:
        return None
