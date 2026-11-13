# QoSI TP3: mecanismos de QoS com VNFs

Trabalho Prático 3 de Qualidade de Serviço na Internet (Universidade do Minho, 2026/2027), grupo PL11.

Uma cadeia de quatro funções de rede virtualizadas (VNFs), em contentores Docker, aplica QoS do tipo DiffServ sobre uma topologia emulada semelhante à de um ISP:

```
clientes -- s1 -- VNF1 -- VNF2 -- VNF3 -- VNF4 -- r1 -- s2 -- servidores
```

| VNF | Aspeto de QoS | Ferramenta | Código |
|---|---|---|---|
| 1. Classificador | Classificação e marcação DSCP | nftables | `vnfs/classifier/` |
| 2. Firewall | Controlo de acesso | nftables | `vnfs/firewall/` |
| 3. Policer/Scheduler | Policiamento e agendamento | tc (police, HTB) | `vnfs/qos/` |
| 4. Monitor | Monitorização | nftables, Python, Prometheus, Grafana | `vnfs/monitor/`, `monitoring/` |

A ordem da cadeia e os parâmetros de cada VNF estão em `config/chain.yaml`.

## Ambiente

O projeto corre num Ubuntu 22.04 com Containernet (Mininet com contentores Docker), Docker e Open vSwitch. Há duas formas de o obter.

### Opção A: WSL2 (recomendada em Windows)

Numa consola do Windows, criar uma distribuição dedicada:

```bash
wsl --install Ubuntu-22.04 --name qosi
```

Dentro dela, ativar o systemd em `/etc/wsl.conf` (`[boot]` seguido de `systemd=true`), reiniciá-la com `wsl --terminate qosi` e, na pasta do repositório, instalar tudo (cerca de 20 minutos):

```bash
sudo bash scripts/provision-all.sh
```

O WSL2 desliga a distribuição ao fim de algum tempo sem uso. O Prometheus e o Grafana voltam a arrancar sozinhos quando ela é reaberta; a topologia tem de ser lançada de novo.

### Opção B: máquina virtual com Vagrant e VirtualBox

```bash
vagrant up
```

```bash
vagrant ssh
```

Dentro da VM, o repositório está em `/vagrant`. Em Windows com o Hyper-V ativo (por exemplo, com o WSL2 instalado), o VirtualBox fica muito lento e as medições de atraso deixam de ser fiáveis; nesse caso, usar a opção A.

## Utilização

Todos os comandos correm como root, na raiz do repositório, dentro do ambiente Linux.

| Comando | O que faz |
|---|---|
| `sudo make images` | Constrói as imagens Docker dos nós e das VNFs |
| `sudo make smoke` | Teste rápido do ambiente (dois contentores e um switch) |
| `sudo make test` | Testa cada VNF isoladamente, com tráfego controlado |
| `sudo make run PROFILE=full` | Arranca a topologia e abre a consola do Mininet |
| `sudo make monitoring` | Arranca o Prometheus (porta 9090) e o Grafana (porta 3000) |
| `sudo make demo` | Corre o roteiro da demonstração de uma vez (ver `docs/guia-demonstracao.md`) |
| `sudo /opt/containernet/venv/bin/python3 topology/run.py --demo 120 --stress` | Gera dois minutos de tráfego, para ver o dashboard do Grafana a mexer |
| `sudo make experiments SET=quick` | Corre a campanha de experiências (ver abaixo) |
| `make plots SET=quick` | Gera os gráficos e a tabela-resumo da campanha |
| `sudo make clean` | Limpa os restos de uma topologia que não terminou bem |

Os perfis (`PROFILE`) estão definidos em `config/chain.yaml`:

| Perfil | VNFs ativas |
|---|---|
| `baseline` | Nenhuma: cadeia em modo de passagem, fila FIFO no gargalo |
| `policeonly` | Classificação e policiamento, sem agendamento |
| `sched` | Classificação e agendamento |
| `police` | Classificação, agendamento e policiamento |
| `full` | Cadeia completa, incluindo a firewall |

Na consola do Mininet, por exemplo:

```
h_voip traceroute -n 10.0.2.11
vnf3 tc -s class show dev vnf3-out
vnf2 nft list ruleset
```

A consola tem dois comandos próprios: `profile <nome>` muda de perfil sem reiniciar a topologia e `traffic 20` gera 20 segundos de tráfego e mostra as métricas (`traffic 20 stress` junta vídeo acima do perfil e tráfego não autorizado).

## Experiências

A campanha (`experiments/campaign.py`) corre nove cenários e grava uma linha por fluxo e por corrida em `results/<conjunto>/runs.csv`. Pode ser interrompida e retomada.

| Cenário | O que varia |
|---|---|
| `load` | Número de fluxos TCP em concorrência com VoIP e vídeo |
| `policing` | Débito de uma fonte de vídeo que excede o perfil contratado |
| `flood` | Débito de tráfego UDP não autorizado, a partir de `h_x` |
| `delay`, `loss` | Atraso e perdas na ligação ao núcleo |
| `outage` | Falha de 3 segundos da ligação ao núcleo |
| `queue`, `weights` | Otimização: tamanho das filas e pesos de AF31 e BE |
| `overhead` | Sobrecarga da cadeia face ao encaminhamento direto |

Há dois conjuntos: `quick` (corridas de 15 s, 2 repetições, cerca de uma hora) e `full` (60 s, 5 repetições, cerca de 8 horas). Os resultados de ambos estão em `results/`; os do relatório final são os de `results/full/`. As métricas são medidas pelo `udpgen` com o relógio monotónico, que é comum a todos os contentores. Para o VoIP, os gráficos incluem o MOS estimado pelo modelo E simplificado (Cole e Rosenbluth), a partir do atraso médio e das perdas.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `config/` | Configuração da topologia, da cadeia e dos perfis de teste |
| `topology/` | Construção da rede emulada e geração de tráfego |
| `vnfs/` | Uma pasta por VNF, com o `Dockerfile` e o script `start` |
| `traffic/` | Gerador e recetor UDP que medem atraso, variação do atraso e perdas |
| `monitoring/` | Prometheus, Grafana e o dashboard |
| `experiments/` | Campanha de experiências e geração dos gráficos |
| `results/` | Resultados das campanhas: `runs.csv`, `summary.csv` e figuras |
| `tests/` | Teste do ambiente e testes de cada VNF |
| `scripts/` | Instalação do ambiente, construção das imagens e limpeza |
| `docs/proposta/` | Proposta (Etapa 1), em LaTeX |
| `docs/progresso/` | Relatório de progresso (Etapa 2), em LaTeX |
| `docs/guia-demonstracao.md` | Guia para explicar e demonstrar o trabalho |

## Autores

André Miguel Rego Trindade Pinto (pg65400), Diogo Fernandes Pinto (pg65405) e Francisco José Fidalgo Lage (pg65407).
