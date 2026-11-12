# Atalhos do projeto. Correr como root dentro do ambiente Linux (WSL2 ou VM):
#   sudo make test
PY := /opt/containernet/venv/bin/python3
PROFILE ?= full

.PHONY: images smoke test run monitoring monitoring-stop clean proposta

images: ; bash scripts/build-images.sh
smoke: images ; $(PY) tests/smoke_test.py
test: images ; $(PY) tests/test_vnfs.py
run: images ; $(PY) topology/run.py --profile $(PROFILE)
monitoring: ; bash monitoring/start.sh
monitoring-stop: ; bash monitoring/stop.sh
clean: ; bash scripts/clean.sh
proposta: ; bash scripts/build-doc.sh docs/proposta/proposta.tex
