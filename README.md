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
| `sudo make clean` | Limpa os restos de uma topologia que não terminou bem |

Os perfis (`PROFILE`) estão definidos em `config/chain.yaml`:

| Perfil | VNFs ativas |
|---|---|
| `baseline` | Nenhuma: cadeia em modo de passagem, fila FIFO no gargalo |
| `sched` | Classificação e agendamento |
| `police` | Classificação, agendamento e policiamento |
| `full` | Cadeia completa, incluindo a firewall |

Na consola do Mininet, por exemplo:

```
h_voip traceroute -n 10.0.2.11
vnf3 tc -s class show dev vnf3-out
vnf2 nft list ruleset
```

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `config/` | Configuração da topologia, da cadeia e dos perfis de teste |
| `topology/` | Construção da rede emulada e geração de tráfego |
| `vnfs/` | Uma pasta por VNF, com o `Dockerfile` e o script `start` |
| `traffic/` | Gerador e recetor UDP que medem atraso, variação do atraso e perdas |
| `monitoring/` | Prometheus, Grafana e o dashboard |
| `tests/` | Teste do ambiente e testes de cada VNF |
| `scripts/` | Instalação do ambiente, construção das imagens e limpeza |
| `docs/proposta/` | Proposta (Etapa 1), em LaTeX |

## Autores

André Miguel Rego Trindade Pinto (pg65400), Diogo Fernandes Pinto (pg65405) e Francisco José Fidalgo Lage (pg65407).
