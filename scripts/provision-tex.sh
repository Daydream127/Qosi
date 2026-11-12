#!/usr/bin/env bash
# LaTeX para compilar a proposta e os relatórios dentro da VM.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get install -y --no-install-recommends \
  texlive-latex-recommended texlive-latex-extra texlive-pictures \
  texlive-publishers texlive-lang-portuguese texlive-fonts-recommended \
  lmodern latexmk poppler-utils

echo "provision-tex: ok"
