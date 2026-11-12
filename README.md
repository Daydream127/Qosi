# QoSI TP3: mecanismos de QoS com VNFs

Trabalho Prático 3 de Qualidade de Serviço na Internet (Universidade do Minho, 2026/2027), grupo PL11.

Uma cadeia de quatro funções de rede virtualizadas (VNFs), em contentores Docker, aplica QoS do tipo DiffServ sobre uma topologia emulada semelhante à de um ISP:

| VNF | Aspeto de QoS | Ferramenta |
|---|---|---|
| 1. Classificador | Classificação e marcação DSCP | nftables |
| 2. Firewall | Controlo de acesso | nftables |
| 3. Policer/Escalonador | Policiamento e escalonamento | tc (police, HTB) |
| 4. Monitor | Monitorização | Python, Prometheus, Grafana |

## Ambiente

Todo o trabalho corre numa máquina virtual Ubuntu 22.04 criada com Vagrant e VirtualBox.

```bash
vagrant up
```

```bash
vagrant ssh
```

Dentro da VM, o repositório está em `/vagrant`. O primeiro `vagrant up` demora cerca de 20 minutos, porque instala o Containernet (Mininet com contentores Docker), o Docker, o Open vSwitch e o LaTeX.

## Verificar o ambiente

Dentro da VM, construir a imagem base dos nós e correr o teste de fumo (dois contentores ligados por um switch, com uma ligação limitada a 10 Mbit/s):

```bash
cd /vagrant && sudo docker build -t qosi/base vnfs/base
```

```bash
cd /vagrant && sudo /opt/containernet/venv/bin/python3 tests/smoke_test.py
```

O teste termina com `SMOKE TEST: OK`.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `scripts/` | Scripts de configuração da VM e de compilação dos documentos |
| `vnfs/base/` | Imagem Docker base de todos os nós (clientes, servidores e VNFs) |
| `tests/` | Testes do ambiente |
| `docs/proposta/` | Proposta (Etapa 1), em LaTeX |

## Compilar a proposta

Dentro da VM:

```bash
cd /vagrant && bash scripts/build-doc.sh docs/proposta/proposta.tex
```

## Autores

André Miguel Rego Trindade Pinto (pg65400), Diogo Fernandes Pinto (pg65405) e Francisco José Fidalgo Lage (pg65407).
