# Guia para explicar e demonstrar o trabalho

Este guia serve para o grupo preparar a apresentação do TP3 ao docente. Tem quatro partes: o resumo do trabalho, o roteiro da demonstração ao vivo, a explicação de cada peça e as perguntas mais prováveis.

## 1. O trabalho num minuto

> Construímos um sistema de QoS do tipo DiffServ em que cada função de rede é uma VNF: um contentor Docker que usa mecanismos do kernel Linux. Quatro VNFs em cadeia tratam o tráfego entre os clientes e os servidores: o classificador marca o DSCP, a firewall bloqueia o que não está autorizado, o policer/scheduler limita cada classe ao perfil contratado e dá prioridade ao VoIP, e o monitor conta o tráfego por classe. Com um gargalo de 10 Mbit/s e tráfego TCP a competir, o atraso do VoIP desce de cerca de 110 ms para 5 ms e deixam de existir perdas em VoIP e vídeo.

Os cinco aspetos de QoS do enunciado estão cobertos (o enunciado exige três):

| Aspeto | Onde | Com quê |
|---|---|---|
| Classificação | VNF1 | `nftables` (marcação DSCP) |
| Controlo de acesso | VNF2 | `nftables` (política default-deny) |
| Policiamento | VNF3, à entrada | `tc police` (token bucket) |
| Agendamento | VNF3, à saída | `tc` HTB (três classes) |
| Monitorização | VNF4 e exportadores | `nftables`, Prometheus, Grafana, `udpgen` |

## 2. Preparação

Na véspera, no computador que vai ser usado:

1. Abrir a distribuição do trabalho com `wsl -d qosi`, numa consola do Windows aberta na pasta do repositório. O `wsl` sozinho abre a distribuição por omissão, que não tem o Docker nem o Containernet.
2. Correr `sudo make test` e confirmar `26/26 verificações passaram`.
3. Correr `sudo make monitoring` e abrir `http://localhost:3000` no browser. O dashboard "QoSI TP3" abre sem login.

Todos os comandos `make` deste guia precisam de root, daí o `sudo`. Sem ele, o erro é `permission denied while trying to connect to the docker API`.
4. Fazer o roteiro da secção 3 uma vez do princípio ao fim.

Dez minutos antes da demonstração:

1. Ligar o computador à corrente e fechar aplicações pesadas (as medições de atraso sofrem com o processador ocupado).
2. Abrir duas janelas lado a lado: um terminal WSL e o browser com o Grafana.
3. No Grafana, escolher o intervalo "Last 5 minutes" e a atualização automática de 5 s.
4. No terminal, deixar a topologia já arrancada (passo 1 do roteiro), porque demora cerca de 20 segundos.

## 3. Roteiro da demonstração

A demonstração demora cerca de dez minutos. Todos os comandos a partir do passo 1 são escritos na consola do Mininet (`containernet>`).

### Passo 1: arrancar a topologia

```bash
sudo make run PROFILE=baseline
```

O que dizer: o script lê `config/chain.yaml`, cria os contentores e as ligações e configura cada VNF. Com o perfil `baseline`, as VNFs estão em modo de passagem: é a rede sem QoS.

### Passo 2: mostrar a cadeia

```
h_voip traceroute -n 10.0.2.11
```

O que se vê: seis saltos. Os quatro primeiros são as VNFs (10.0.1.1, 10.0.10.2, 10.0.11.2 e 10.0.12.2), o quinto é o encaminhador do núcleo `r1` (10.0.13.2) e o sexto é o destino.

O que dizer: cada VNF é um salto IP, e todo o tráfego dos clientes é obrigado a atravessar a cadeia pela ordem definida no ficheiro de configuração.

Dois pormenores. Os tempos dos saltos 5 e 6 (cerca de 10 e 20 ms) incluem a resolução ARP, que também atravessa a ligação com atraso; um `ping` a seguir mostra 10 ms de ida e volta. E o `traceroute` só funciona neste perfil: com a firewall ativa, as sondas são bloqueadas na VNF2.

### Passo 3: a rede sem QoS

```
traffic 20
```

O comando gera durante 20 segundos uma chamada VoIP (80 kbit/s), vídeo (4 Mbit/s) e quatro fluxos TCP, e mostra as métricas medidas.

O que se vê: o VoIP com atraso p95 perto de 110 ms e algumas perdas em VoIP e vídeo.

O que dizer: o gargalo tem 10 Mbit/s e uma única fila. O TCP enche a fila e todos os pacotes esperam o mesmo, incluindo os do VoIP. O objetivo da classe 0 da Y.1541 é 100 ms, e já não é cumprido.

### Passo 4: ligar a cadeia completa

```
profile full
traffic 20
```

O que se vê: cada VNF anuncia que ficou ativa. O atraso p95 do VoIP passa para cerca de 5 ms (o atraso do núcleo), sem perdas em VoIP e vídeo, e o TCP continua com perto de 5 Mbit/s.

O que dizer: a topologia é a mesma; só mudou a configuração das VNFs. O classificador marca o VoIP como EF, e o scheduler serve essa classe primeiro.

### Passo 5: classificação e monitorização

```
vnf1 nft list counters
vnf4 nft list counters
```

O que se vê: na VNF1, os contadores `voip`, `video` e `other`. Na VNF4, os contadores `class_ef`, `class_af31` e `class_be`, que contam pela marca DSCP dos pacotes.

O que dizer: a VNF4 só vê a marca DSCP. Os números de `class_ef` são iguais aos de `voip` (cerca de 1005 pacotes) e os de `class_af31` iguais aos de `video` (cerca de 8005): a marcação feita na VNF1 chegou ao fim da cadeia. Estes contadores são os que o Prometheus recolhe e o Grafana mostra.

Dois pormenores. Os contadores recomeçam do zero quando se muda de perfil, por isso mostram só o último `traffic`. E `other` é maior do que `class_be`, porque a VNF1 conta também o tráfego de retorno (os ACK do TCP) e a VNF4 só conta o sentido dos clientes para os servidores.

### Passo 6: controlo de acesso

```
h_x ping -c 2 -W 1 10.0.2.11
h_voip ping -c 2 10.0.2.11
vnf2 nft list counter ip firewall dropped
```

O que se vê: o `h_x` tem 100% de perdas, o `h_voip` tem resposta em cerca de 10 ms, e o contador mostra 2 pacotes descartados (os dois pings do `h_x`).

O que dizer: a firewall tem política default-deny. Só passam os clientes e as portas da lista; o `h_x` não está na lista.

### Passo 7: policiamento e tráfego não autorizado

```
traffic 20 stress
vnf3 tc -s filter show dev vnf3-in parent ffff:
vnf3 tc -s class show dev vnf3-out
```

Com `stress`, a fonte de vídeo envia 6 Mbit/s (o perfil contratado é 5 Mbit/s) e o `h_x` envia 2 Mbit/s.

O que se vê: o vídeo recebido fica em 5 Mbit/s, com cerca de 16% de perdas; o `h_x` tem 4000 pacotes enviados e 0 entregues; o VoIP continua nos 5 ms. No primeiro comando do `tc` aparecem os dois policiadores: o de EF (`rate 200Kbit`) sem descartes e o de AF31 (`rate 5Mbit`) com cerca de 1900 (`dropped`). No segundo aparecem as três classes HTB: `1:10` é EF, `1:20` é AF31 e `1:30` é BE, cada uma com os bytes enviados e os descartes.

O que dizer: o policiador protege a rede de uma fonte que não cumpre o contrato. Quem excede o perfil perde o excesso; os outros fluxos não são afetados.

Durante este passo, mostrar o Grafana: o painel do policiador mostra cerca de 100 pacotes por segundo descartados, e o da firewall cerca de 200 bloqueados.

### Passo 8: fechar

```
exit
```

A seguir, mostrar os gráficos da campanha (secção 5).

### Alternativa: correr o roteiro de uma vez

Os comandos dos passos 2 a 7 estão em `docs/demo-comandos.txt`. O comando seguinte arranca a topologia, corre-os todos pela ordem e sai; demora cerca de dois minutos. Serve para ensaiar e como recurso se houver pouco tempo.

```bash
sudo make demo
```

## 4. Como explicar cada parte

### Porque é que isto é NFV

Numa rede tradicional, cada função (firewall, equipamento de QoS, sonda) é uma caixa dedicada. Em NFV, a função é software que corre em hardware comum. Aqui, cada VNF é uma imagem Docker com um script `start`. Em termos da arquitetura ETSI NFV: a infraestrutura (NFVI) é o Docker, o Open vSwitch e o Containernet; as VNFs são os quatro contentores; e o papel de orquestrador é feito, de forma simplificada, pelo script `topology/qosnet.py`, que cria as VNFs, as liga em cadeia e as configura a partir de `config/chain.yaml`.

### VNF1 Classificador

Olha para o destino, o protocolo e a porta de cada pacote e escreve a marca DSCP: EF (46) para VoIP, AF31 (26) para vídeo e 0 para o resto, segundo o RFC 4594. Remarca também o que já vinha marcado pelos clientes, porque a fronteira de um domínio DiffServ não confia na marcação de fora: se confiasse, qualquer cliente marcava o seu tráfego como EF.

### VNF2 Firewall

Tem uma lista de clientes e de portas autorizados. O que não está na lista é descartado e contado. Aceita também os pacotes de ligações já estabelecidas, para as respostas dos servidores passarem.

### VNF3 Policer/Scheduler

Faz duas coisas diferentes, em sítios diferentes:

- **Policiamento, à entrada.** Um token bucket por classe. O balde enche ao débito contratado e cada pacote gasta fichas; se não houver fichas, o pacote é descartado. O tamanho do balde define a rajada tolerada. EF tem 200 kbit/s e AF31 tem 5 Mbit/s.
- **Agendamento, à saída.** A saída da VNF3 é o gargalo de 10 Mbit/s, e é aí que a fila se forma. O HTB divide a capacidade em três classes. EF é servida primeiro e está limitada a 1 Mbit/s, para nunca poder esgotar as outras. AF31 tem 5 Mbit/s garantidos e BE tem 4 Mbit/s; o que sobrar é emprestado, primeiro a AF31 e depois a BE.

A diferença entre policiar e moldar (shaping): o policiador descarta o excesso, o shaper atrasa-o numa fila. Usamos policiamento à entrada e filas só no gargalo.

### VNF4 Monitor e medição

Há dois tipos de medição:

- **Passiva.** Contadores por classe na VNF4 e estatísticas do `tc` na VNF3 (ocupação das filas, descartes). Um pequeno exportador em Python, em cada VNF, publica-os; o Prometheus recolhe-os de segundo a segundo e o Grafana desenha-os.
- **Ativa.** O gerador `udpgen` põe em cada pacote um número de sequência e o instante de envio. O recetor calcula o atraso num sentido (IPTD), a variação do atraso (IPDV), as perdas (IPLR) e o débito. O atraso num sentido é fiável porque todos os contentores partilham o relógio monotónico da máquina: não há erro de sincronização.

### Perfis

Um perfil é um conjunto de alterações às variáveis das VNFs. Permite comparar configurações sobre a mesma topologia:

| Perfil | O que está ativo |
|---|---|
| `baseline` | Nada: fila única no gargalo |
| `policeonly` | Classificação e policiamento |
| `sched` | Classificação e agendamento |
| `police` | Classificação, agendamento e policiamento |
| `full` | Tudo, incluindo a firewall |

## 5. Resultados a mostrar

Os resultados são da campanha completa: 420 corridas de 60 s, cinco repetições por ponto, médias com intervalo de confiança de 95%. Os gráficos estão em `results/full/figures/` e os números em `results/full/summary.csv`.

O resultado principal, com VoIP, vídeo e quatro fluxos TCP no gargalo de 10 Mbit/s:

| Configuração | Atraso VoIP (p95) | IPDV VoIP | Perdas VoIP | Perdas vídeo | Débito TCP |
|---|---|---|---|---|---|
| Sem QoS | 108,8 ms | 5,6 ms | 0,52% | 0,35% | 5,66 Mbit/s |
| Agendamento | 5,3 ms | 0,08 ms | 0% | 0% | 5,49 Mbit/s |
| Agendamento e policiamento | 5,4 ms | 0,10 ms | 0% | 0% | 5,37 Mbit/s |
| Cadeia completa | 5,4 ms | 0,09 ms | 0% | 0% | 5,43 Mbit/s |

O que cada gráfico mostra:

| Gráfico | Mensagem |
|---|---|
| [load](../results/full/figures/load.png) | Com QoS, o VoIP e o vídeo ficam isolados da carga: o atraso mantém-se em 5 ms com 1 ou com 8 fluxos TCP. O custo para o TCP é pequeno. |
| [policing](../results/full/figures/policing.png) | Com a fonte de vídeo a enviar 12 Mbit/s e sem QoS, o TCP fica com 0,34 Mbit/s e o VoIP perde 52% dos pacotes. O policiador limita o vídeo a 5,0 Mbit/s e o TCP mantém 4,5 Mbit/s. Só com policiamento, sem agendamento, o débito fica protegido mas o atraso do VoIP continua em 107 ms: são precisos os dois. |
| [flood](../results/full/figures/flood.png) | Com 12 Mbit/s de tráfego não autorizado, o agendamento protege o VoIP e o vídeo, mas o TCP fica com 0,30 Mbit/s. Só com a firewall o TCP mantém 5,5 Mbit/s. |
| [mos](../results/full/figures/mos.png) | Com a cadeia, o MOS estimado do VoIP é sempre 4,4. Sem QoS desce para 1,5 com vídeo fora do perfil e para 1,3 com tráfego não autorizado. |
| [queue](../results/full/figures/queue.png) | Otimização: filas maiores não dão mais débito ao TCP e aumentam o atraso da classe best effort (p95 de 44 ms com 20 pacotes, 592 ms com 300). O VoIP não é afetado. |
| [weights](../results/full/figures/weights.png) | Otimização: com vídeo a 6 Mbit/s, garantir só 3 Mbit/s a AF31 dá 35% de perdas no vídeo; com 5 Mbit/s dá 2,2% e com 7 Mbit/s nenhuma, à custa do TCP (5,6, 3,8 e 3,6 Mbit/s). |
| [bucket](../results/full/figures/bucket.png) | Otimização: com o vídeo dentro do perfil mas em rajadas de 20 kB (um frame), um balde de 5 kB no policiador descarta 75% dos pacotes e um de 10 kB descarta 50%; a partir de 20 kB não há perdas. O balde tem de comportar a maior rajada legítima. |
| [delay](../results/full/figures/delay.png) | A cadeia não elimina o atraso do núcleo, mas retira-lhe o atraso da fila: com 100 ms no núcleo, o VoIP tem 100 ms (p95) com a cadeia e 202 ms sem ela. |
| [loss](../results/full/figures/loss.png) | As perdas no núcleo acontecem depois da cadeia e afetam todas as configurações por igual: o QoS no acesso não as corrige. |
| [outage](../results/full/figures/outage.png) | Depois de uma falha de 3 s na ligação ao núcleo, o VoIP volta logo aos 5 ms com a cadeia. Sem QoS, volta aos 100 ms assim que o TCP recupera. |
| [overhead](../results/full/figures/overhead.png) | Sem o limite de 10 Mbit/s, o encaminhamento direto atinge 8,7 Gbit/s e a cadeia 2,8 Gbit/s. Com carga, a cadeia acrescenta cerca de 0,03 ms de atraso. Sem carga, a diferença perde-se no ruído do despertar do processador. |

Sem QoS, as perdas de VoIP e de vídeo variam muito de corrida para corrida (barras de erro grandes). É o comportamento esperado de uma fila única com descarte à cauda: quem perde depende do instante em que cada pacote chega à fila cheia.

## 6. Perguntas prováveis

**Onde está o congestionamento?**
Na saída da VNF3, limitada a 10 Mbit/s. As outras ligações são virtuais e muito mais rápidas. O tráfego oferecido (80 kbit/s de VoIP, 4 Mbit/s de vídeo e TCP sem limite) excede sempre essa capacidade.

**Porque é que, sem QoS, o atraso do VoIP é cerca de 110 ms?**
A fila tem 100 pacotes. Cheia de pacotes TCP de 1500 bytes, demora 100 × 1500 × 8 / 10 Mbit/s = 120 ms a esvaziar. Um pacote VoIP que chega ao fim da fila espera quase isso, mais os 5 ms do núcleo.

**Porque é que o TCP não fica sem débito com o agendamento?**
A classe BE tem 4 Mbit/s garantidos e pode usar o que as outras não usam. Com VoIP e vídeo dentro do perfil sobram quase 6 Mbit/s, e o TCP obtém cerca de 5,4.

**Porque é que EF está limitada a 1 Mbit/s?**
Uma classe com prioridade absoluta e sem limite pode deixar as outras sem serviço. O limite de 1 Mbit/s no scheduler e o policiador de 200 kbit/s à entrada garantem que isso não acontece.

**O policiador de EF está a 200 kbit/s, mas no teste passam 216 kbit/s. Porquê?**
Por causa da rajada. O balde começa cheio (10 kB), e num teste curto essas fichas iniciais contam: 10 kB em 5 s são mais 16 kbit/s.

**Como é que medem o atraso num sentido sem sincronizar relógios?**
Emissor e recetor são contentores na mesma máquina e leem o mesmo relógio monotónico. Numa rede real seria preciso sincronização (GPS ou PTP) ou medir ida e volta.

**Porque é que o MOS quase não muda só com carga TCP?**
Com 110 ms de atraso e perdas abaixo de 1%, uma chamada ainda é boa: o modelo E só penaliza muito o atraso acima de 177 ms. O MOS cai a sério quando há perdas grandes, como nos cenários de vídeo fora do perfil e de tráfego não autorizado.

**Quanto custa a cadeia?**
Sem o limite de 10 Mbit/s, o débito máximo desce de 8,7 Gbit/s (encaminhamento direto) para 2,8 Gbit/s, e o atraso sobe cerca de 0,03 ms. Para um gargalo de 10 Mbit/s, o custo é desprezável. Os valores absolutos dependem da máquina.

**Como se troca a ordem das VNFs ou se acrescenta uma?**
Edita-se a lista `chain` em `config/chain.yaml`. Os endereços e as rotas são gerados a partir da lista. Uma VNF nova é uma pasta em `vnfs/` com um `Dockerfile` e um script `start`.

**Porque `nftables` e `tc`, e não SDN com OpenFlow?**
São os mecanismos de QoS nativos do Linux, os mesmos que um router Linux real usaria, e são simples de inspecionar e de explicar. O Open vSwitch é usado só como comutador.

**O que acontece se uma VNF falhar?**
A cadeia é em série, por isso o tráfego pára. Não implementámos redundância nem recuperação automática; num sistema real, o orquestrador vigiaria as VNFs e relançava-as.

**Quais são as limitações?**
É uma emulação numa só máquina, com tráfego sintético de débito constante. A classificação é por portas, não pelo conteúdo. A cadeia é estática: não há escalonamento automático das VNFs. O MOS é uma estimativa a partir do atraso e das perdas, que assume 60 ms de atraso nos terminais.

**Usaram IA?**
A UC permite. Respondam com transparência sobre como a usaram; o que conta é saberem explicar cada parte, e este guia serve para isso.

## 7. Se algo correr mal

| Problema | O que fazer |
|---|---|
| `docker: command not found` | Está aberta a distribuição errada: sair com `exit` e abrir com `wsl -d qosi` |
| `permission denied` ao ligar ao Docker | Falta o `sudo` antes do `make` |
| A topologia não arranca ou ficou presa | Sair com `exit` ou Ctrl+C, correr `sudo make clean` e voltar a arrancar |
| O Grafana não abre | Correr `sudo make monitoring`; confirmar que o WSL2 não foi desligado |
| O Grafana abre mas não tem dados | A topologia tem de estar a correr; confirmar o intervalo "Last 5 minutes" |
| Os atrasos estão estranhos | Fechar aplicações pesadas e repetir; ligar o computador à corrente |
| Não há tempo ou a rede falha | Mostrar a captura do Grafana e a saída do `make test` do relatório de progresso |

## 8. Divisão sugerida

Com três elementos, uma divisão simples: um apresenta a arquitetura e as VNFs (secção 4), outro conduz a demonstração (secção 3) e o terceiro apresenta os resultados e as limitações (secções 5 e 6). Todos devem conseguir responder às perguntas da secção 6.
