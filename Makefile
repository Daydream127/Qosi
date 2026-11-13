# Atalhos do projeto. Correr como root dentro do ambiente Linux (WSL2 ou VM):
#   sudo make test
PY := /opt/containernet/venv/bin/python3
PROFILE ?= full

SET ?= quick

.PHONY: images smoke test run demomonitoring monitoring-stop clean proposta progresso relatorio experiments plots

images: ; bash scripts/build-images.sh
smoke: images ; $(PY) tests/smoke_test.py
test: images ; $(PY) tests/test_vnfs.py
run: images ; $(PY) topology/run.py --profile $(PROFILE)
demo: images ; $(PY) topology/run.py --profile baseline --script docs/demo-comandos.txt
monitoring: ; bash monitoring/start.sh
monitoring-stop: ; bash monitoring/stop.sh
experiments: images ; $(PY) experiments/campaign.py --set $(SET) && python3 experiments/plot.py --set $(SET)
plots: ; python3 experiments/plot.py --set $(SET)
clean: ; bash scripts/clean.sh
proposta: ; bash scripts/build-doc.sh docs/proposta/proposta.tex
progresso: ; bash scripts/build-doc.sh docs/progresso/progresso.tex
relatorio: ; bash scripts/build-doc.sh docs/relatorio/relatorio.tex
