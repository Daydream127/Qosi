#!/usr/bin/env python3
"""Gráficos e tabela-resumo da campanha de experiências.

Lê results/<conjunto>/runs.csv e escreve, na mesma pasta:
  - summary.csv: média e intervalo de confiança de 95% de cada métrica;
  - figures/<cenário>.pdf e .png: um gráfico por cenário. As barras de erro são
    o intervalo de confiança de 95% ou, com menos de três repetições, o mínimo
    e o máximo observados.

    python3 experiments/plot.py --set quick
"""
import argparse
import csv
import math
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cada perfil tem sempre a mesma cor e o mesmo marcador, em todos os gráficos.
PROFILES = {
    "baseline":   ("Sem QoS",                      "#2a78d6", "o"),
    "sched":      ("Agendamento",                  "#eb6834", "s"),
    "police":     ("Agendamento + policiamento",   "#1baf7a", "^"),
    "full":       ("Cadeia completa",              "#eda100", "D"),
    "policeonly": ("Só policiamento",              "#e87ba4", "v"),
    "direto":     ("Sem cadeia (direto)",          "#008300", "P"),
}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#d9d8d2"

# Valor crítico do t de Student (95%, bilateral) por graus de liberdade.
T95 = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36, 8: 2.31, 9: 2.26}


# Atraso fixo dos terminais somado ao atraso da rede na estimativa do MOS:
# 20 ms de empacotamento (G.711) e 40 ms de buffer de compensação de jitter.
TERMINAL_DELAY_MS = 60.0


def mos(owd_ms, loss_ratio):
    """MOS estimado de uma chamada G.711, pelo modelo E simplificado.

    Cole e Rosenbluth (2001): R = 94,2 - Id - Ie, em que Id penaliza o atraso
    boca-ouvido d (mais a partir de 177,3 ms) e Ie penaliza as perdas.
    """
    delay = owd_ms + TERMINAL_DELAY_MS
    impairment_delay = 0.024 * delay + (0.11 * (delay - 177.3) if delay > 177.3 else 0.0)
    impairment_loss = 30 * math.log(1 + 15 * loss_ratio)
    r = 94.2 - impairment_delay - impairment_loss
    if r <= 0:
        return 1.0
    if r >= 100:
        return 4.5
    return 1 + 0.035 * r + 7e-6 * r * (r - 60) * (100 - r)


def load(path):
    """{(cenário, perfil, x, fluxo): {métrica: [valores das repetições]}}"""
    data = defaultdict(lambda: defaultdict(list))
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["experiment"], row["profile"], row["x"], row["flow"])
            for name, value in row.items():
                try:
                    data[key][name].append(float(value))
                except (TypeError, ValueError):
                    pass
            if row["flow"] == "voip" and row["loss_ratio"]:
                # Sem pacotes recebidos não há atraso medido; contam só as perdas.
                data[key]["mos"].append(mos(float(row["owd_ms_mean"] or 0),
                                            float(row["loss_ratio"])))
    return data


def mean_ci(values):
    n = len(values)
    if n == 0:
        return None, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    deviation = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    return mean, T95.get(n - 1, 1.96) * deviation / math.sqrt(n)


def whiskers(values, metric, scale):
    """(média, erro inferior, erro superior), já na escala do gráfico.

    Com três ou mais repetições, as barras de erro são o intervalo de confiança
    de 95%; com menos, o intervalo de confiança não diz nada de útil e as barras
    vão do mínimo ao máximo observados.
    """
    mean, ci = mean_ci(values)
    if mean is None:
        return None
    low, high = (mean - ci, mean + ci) if len(values) >= 3 else (min(values), max(values))
    low = max(low, 0.0)                    # nenhuma das métricas é negativa
    if metric == "loss_ratio":
        high = min(high, 1.0)
    return mean * scale, (mean - low) * scale, (high - mean) * scale


def x_values(data, experiment, flow, metric):
    """Valores de x com dados: por ordem numérica ou, se forem nomes, pela da campanha."""
    seen = list(dict.fromkeys(key[2] for key, metrics in data.items()
                              if key[0] == experiment and key[3] == flow and metrics.get(metric)))
    try:
        return sorted(seen, key=float)
    except ValueError:
        return seen


def profiles_of(data, experiment):
    present = {key[1] for key in data if key[0] == experiment}
    return [name for name in PROFILES if name in present]


def style(ax, ylabel, xlabel):
    ax.set_ylabel(ylabel, color=INK)
    ax.set_xlabel(xlabel, color=INK)
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)


def lines(ax, data, experiment, flow, metric, scale=1.0):
    """Uma linha por perfil, com barras de erro (ver whiskers), sobre x categórico."""
    xs = x_values(data, experiment, flow, metric)
    for profile in profiles_of(data, experiment):
        label, color, marker = PROFILES[profile]
        points = [(i, whiskers(data.get((experiment, profile, x, flow), {}).get(metric, []),
                               metric, scale)) for i, x in enumerate(xs)]
        points = [(i, *w) for i, w in points if w is not None]
        if not points:
            continue
        ax.errorbar([p[0] for p in points], [p[1] for p in points],
                    yerr=[[p[2] for p in points], [p[3] for p in points]],
                    label=label, color=color, marker=marker,
                    linewidth=2, markersize=6.5, markeredgecolor="white", markeredgewidth=1,
                    capsize=2.5, elinewidth=1)
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs)


def bars(ax, data, experiment, flow, metric, scale=1.0):
    """Barras agrupadas por x, uma por perfil, com barras de erro (ver whiskers)."""
    xs = x_values(data, experiment, flow, metric)
    profiles = profiles_of(data, experiment)
    width = 0.8 / max(1, len(profiles))
    for index, profile in enumerate(profiles):
        label, color, _ = PROFILES[profile]
        for i, x in enumerate(xs):
            point = whiskers(data.get((experiment, profile, x, flow), {}).get(metric, []),
                             metric, scale)
            if point is None:
                continue
            mean, low, high = point
            position = i - 0.4 + width * (index + 0.5)
            ax.bar(position, mean, width * 0.9, yerr=[[low], [high]], color=color,
                   label=label if i == 0 else None, capsize=2.5,
                   error_kw={"elinewidth": 1, "ecolor": INK})
            ax.annotate(f"{mean:.3g}", (position, mean + high),
                        textcoords="offset points", xytext=(0, 2), ha="center",
                        fontsize=7, color=INK)
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs)


def figure(panels, path, xlabel, kind=lines, columns=2):
    """panels: lista de (título do eixo y, argumentos de lines/bars).

    xlabel é um título comum ou uma lista com um título por painel.
    """
    rows = math.ceil(len(panels) / columns)
    xlabels = xlabel if isinstance(xlabel, list) else [xlabel] * len(panels)
    fig, axes = plt.subplots(rows, columns, figsize=(6.4, 2.35 * rows + 0.45), squeeze=False)
    for ax, (ylabel, args), label in zip(axes.flat, panels, xlabels):
        kind(ax, *args)
        style(ax, ylabel, label)
        if args[3] == "mos":  # a escala do MOS vai de 1 (mau) a 4,5 (excelente)
            ax.set_ylim(1, 4.6)
    for ax in axes.flat[len(panels):]:
        ax.set_visible(False)
    # Legenda comum: cada perfil aparece uma vez, mesmo que falte nalgum painel.
    entries = {}
    for ax in axes.flat:
        for handle, label in zip(*ax.get_legend_handles_labels()):
            entries.setdefault(label, handle)
    order = [label for label, _, _ in PROFILES.values() if label in entries]
    handles, labels = [entries[label] for label in order], order
    legend_height = 0.0
    if len(labels) > 1:  # com uma só série, o título do eixo chega
        per_row = len(labels) if len(labels) <= 4 else 3
        legend_height = 0.12 + 0.2 * math.ceil(len(labels) / per_row)
        fig.legend(handles, labels, loc="upper center", ncol=per_row,
                   frameon=False, fontsize=8, handlelength=1.6, columnspacing=1.2)
    fig.tight_layout(rect=(0, 0, 1, 1 - legend_height / fig.get_figheight()))
    save(fig, path)


def save(fig, path):
    """Grava em PDF e PNG. Sem data no PDF, o ficheiro só muda se o gráfico mudar."""
    fig.savefig(f"{path}.pdf", metadata={"CreationDate": None})
    fig.savefig(f"{path}.png", dpi=200)
    plt.close(fig)


def outage_figure(out_dir, path):
    """Atraso do VoIP ao longo do tempo, com uma falha da ligação a meio."""
    files = {profile: os.path.join(out_dir, "packets", f"outage-{profile}-3-1.csv")
             for profile in ("baseline", "full")}
    files = {profile: name for profile, name in files.items() if os.path.exists(name)}
    if not files:
        return
    # Mesma escala nos dois painéis, para a comparação ser direta.
    fig, axes = plt.subplots(1, len(files), figsize=(6.4, 2.6), squeeze=False, sharey=True)
    for ax, (profile, name) in zip(axes.flat, files.items()):
        with open(name, newline="") as handle:
            rows = [(float(r["t_ms"]) / 1000, float(r["owd_ms"])) for r in csv.DictReader(handle)]
        label, color, _ = PROFILES[profile]
        # A linha é interrompida onde faltam pacotes; o maior intervalo é a falha.
        times, delays, widest = [], [], (0.0, 0.0)
        for (t0, _), (t1, owd) in zip([rows[0]] + rows, rows):
            if t1 - t0 > 0.1:
                times.append(float("nan"))
                delays.append(float("nan"))
                if t1 - t0 > widest[1] - widest[0]:
                    widest = (t0, t1)
            times.append(t1)
            delays.append(owd)
        ax.plot(times, delays, color=color, linewidth=1.2)
        if widest[1] > widest[0]:
            ax.axvspan(*widest, color=GRID, alpha=0.6, linewidth=0)
            ax.annotate("falha", ((widest[0] + widest[1]) / 2, 0.92),
                        xycoords=("data", "axes fraction"), ha="center", fontsize=8, color=MUTED)
        ax.set_title(label, fontsize=9, color=INK)
        style(ax, "Atraso VoIP (ms)", "Tempo (s)")
    fig.tight_layout()
    save(fig, path)


def write_summary(data, path):
    metrics = ["loss_ratio", "owd_ms_mean", "owd_ms_p95", "owd_ms_p99", "ipdv_ms_mean",
               "jitter_rfc3550_ms", "throughput_kbps", "mos"]
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["experiment", "profile", "x", "flow", "runs"]
                        + [f"{m}{suffix}" for m in metrics for suffix in ("", "_ci95")])
        for key in sorted(data):
            row = list(key) + [len(data[key].get("rep", []))]
            for metric in metrics:
                mean, ci = mean_ci(data[key].get(metric, []))
                row += ["" if mean is None else round(mean, 4), round(ci, 4)]
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", default="quick")
    args = parser.parse_args()

    out_dir = os.path.join(ROOT, "results", args.set)
    data = load(os.path.join(out_dir, "runs.csv"))
    figures = os.path.join(out_dir, "figures")
    os.makedirs(figures, exist_ok=True)
    plt.rcParams.update({"font.size": 8.5, "axes.labelsize": 8.5, "font.family": "DejaVu Sans"})
    experiments = {key[0] for key in data}

    def path(name):
        return os.path.join(figures, name)

    if "load" in experiments:
        figure([("Atraso VoIP, p95 (ms)", (data, "load", "voip", "owd_ms_p95")),
                ("Perdas VoIP (%)", (data, "load", "voip", "loss_ratio", 100)),
                ("Perdas vídeo (%)", (data, "load", "video", "loss_ratio", 100)),
                ("Débito TCP (Mbit/s)", (data, "load", "bulk", "throughput_kbps", 0.001))],
               path("load"), "Fluxos TCP em concorrência")
    if "policing" in experiments:
        figure([("Débito TCP (Mbit/s)", (data, "policing", "bulk", "throughput_kbps", 0.001)),
                ("Vídeo recebido (Mbit/s)", (data, "policing", "video", "throughput_kbps", 0.001)),
                ("Atraso VoIP, p95 (ms)", (data, "policing", "voip", "owd_ms_p95")),
                ("Perdas VoIP (%)", (data, "policing", "voip", "loss_ratio", 100))],
               path("policing"), "Débito enviado pela fonte de vídeo (Mbit/s)")
    if "flood" in experiments:
        figure([("Débito TCP (Mbit/s)", (data, "flood", "bulk", "throughput_kbps", 0.001)),
                ("Atraso VoIP, p95 (ms)", (data, "flood", "voip", "owd_ms_p95")),
                ("Perdas vídeo (%)", (data, "flood", "video", "loss_ratio", 100)),
                ("Tráfego de h_x entregue (Mbit/s)",
                 (data, "flood", "flood", "throughput_kbps", 0.001))],
               path("flood"), "Débito do tráfego não autorizado (Mbit/s)")
    if "delay" in experiments:
        figure([("Atraso VoIP, média (ms)", (data, "delay", "voip", "owd_ms_mean")),
                ("Atraso VoIP, p95 (ms)", (data, "delay", "voip", "owd_ms_p95"))],
               path("delay"), "Atraso na ligação ao núcleo (ms)")
    if "loss" in experiments:
        figure([("Perdas VoIP (%)", (data, "loss", "voip", "loss_ratio", 100)),
                ("Débito TCP (Mbit/s)", (data, "loss", "bulk", "throughput_kbps", 0.001))],
               path("loss"), "Perdas na ligação ao núcleo (%)")
    if "queue" in experiments:
        figure([("Atraso best effort, p95 (ms)", (data, "queue", "be_probe", "owd_ms_p95")),
                ("Débito TCP (Mbit/s)", (data, "queue", "bulk", "throughput_kbps", 0.001))],
               path("queue"), "Tamanho das filas (pacotes)")
    if "weights" in experiments:
        figure([("Perdas vídeo (%)", (data, "weights", "video", "loss_ratio", 100)),
                ("Débito TCP (Mbit/s)", (data, "weights", "bulk", "throughput_kbps", 0.001))],
               path("weights"), "Débito garantido AF31/BE (Mbit/s)", kind=bars)
    if "overhead" in experiments:
        figure([("Atraso VoIP, média (ms)", (data, "overhead", "voip", "owd_ms_mean")),
                ("Débito TCP (Gbit/s)", (data, "overhead", "bulk", "throughput_kbps", 1e-6))],
               path("overhead"), "", kind=bars)
    if "outage" in experiments:
        outage_figure(out_dir, path("outage"))
    with_mos = [(name, label) for name, label in (
        ("load", "Fluxos TCP em concorrência"),
        ("policing", "Débito da fonte de vídeo (Mbit/s)"),
        ("flood", "Tráfego não autorizado (Mbit/s)"),
        ("delay", "Atraso na ligação ao núcleo (ms)")) if name in experiments]
    if with_mos:
        figure([("MOS estimado (VoIP)", (data, name, "voip", "mos")) for name, _ in with_mos],
               path("mos"), [label for _, label in with_mos])

    write_summary(data, os.path.join(out_dir, "summary.csv"))
    print(f"figuras em {figures}")


if __name__ == "__main__":
    main()
