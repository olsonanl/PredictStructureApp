#!/usr/bin/env bash
# Generate MSAs for the medium/large test fixtures via the ColabFold MSA
# server (mmseqs2 web). Run ONCE, out-of-band; the resulting .a3m files
# are committed to the repo so tests stay offline.
#
# Re-run this when the fixtures change. The output filenames must match
# tests/acceptance/matrix.py constants:
#   medium_protein.fasta -> test_data/msa/medium_protein.a3m
#   large_protein.fasta  -> test_data/msa/large_protein.a3m
#
# Requirements:
#   - colabfold_search (from ColabFold/MMseqs2). Available inside
#     /scout/containers/folding_prod.sif under
#     /opt/conda-colabfold/bin/colabfold_search (verify path with
#     `apptainer exec <sif> which colabfold_search`).
#   - Network access to colabfold MSA server, OR local MMseqs2 databases.
#
# Cost: ~1-5 minutes per query against the server. ~5-100 KB output per fixture.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TEST_DATA="$REPO/test_data"
MSA_DIR="$TEST_DATA/msa"
mkdir -p "$MSA_DIR"

SIF="${PREDICT_STRUCTURE_SIF:-/scout/containers/folding_prod.sif}"
if [ ! -f "$SIF" ]; then
    echo "ERROR: SIF not found: $SIF" >&2
    echo "Set PREDICT_STRUCTURE_SIF=<path-to-sif> and re-run." >&2
    exit 1
fi

# colabfold_search inside the SIF -- adjust if path differs.
COLABFOLD_SEARCH="${COLABFOLD_SEARCH:-/opt/conda-colabfold/bin/colabfold_search}"

run_one() {
    local fasta="$1"
    local out_basename="$2"
    local tmp="$(mktemp -d)"
    echo "=== Generating MSA for $fasta -> $out_basename.a3m ==="
    apptainer exec --bind "$TEST_DATA":/data --bind "$tmp":/tmp_msa "$SIF" \
        "$COLABFOLD_SEARCH" \
        "/data/$(basename "$fasta")" \
        /tmp_msa \
        --use-env 1 --use-templates 0 --filter 1
    # ColabFold writes 0.a3m (or <name>.a3m depending on version)
    a3m=$(ls "$tmp"/*.a3m 2>/dev/null | head -1)
    if [ -z "$a3m" ]; then
        echo "ERROR: no .a3m produced in $tmp" >&2
        rm -rf "$tmp"
        exit 1
    fi
    cp "$a3m" "$MSA_DIR/${out_basename}.a3m"
    rm -rf "$tmp"
    echo "  -> $MSA_DIR/${out_basename}.a3m ($(wc -l < "$MSA_DIR/${out_basename}.a3m") lines)"
}

run_one "$TEST_DATA/medium_protein.fasta" medium_protein
run_one "$TEST_DATA/large_protein.fasta"  large_protein

echo
echo "Done. Commit the new .a3m files in $MSA_DIR/."
