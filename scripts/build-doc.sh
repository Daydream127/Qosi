#!/usr/bin/env bash
# Compila um documento LaTeX dentro da VM.
#   scripts/build-doc.sh docs/proposta/proposta.tex
# A compilação é feita em /tmp (mais rápido do que na pasta partilhada) e o PDF
# é copiado para junto do .tex. Com PREVIEW=1 gera também PNGs em .preview/.
set -euo pipefail

tex="$(readlink -f "$1")"
dir="$(dirname "$tex")"
name="$(basename "$tex" .tex)"
out="/tmp/latex-$name"

cd "$dir"
latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir="$out" "$name.tex" \
  > "$out.log" 2>&1 || { tail -40 "$out.log"; exit 1; }
cp "$out/$name.pdf" "$dir/$name.pdf"

grep -E "^!|Overfull|undefined" "$out/$name.log" || true
pdfinfo "$dir/$name.pdf" | grep -E "Pages|Page size"

if [ "${PREVIEW:-0}" = "1" ]; then
  root="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null || echo /vagrant)"
  mkdir -p "$root/.preview"
  rm -f "$root/.preview/$name"-*.png
  pdftoppm -r "${DPI:-80}" -png "$dir/$name.pdf" "$root/.preview/$name"
fi
