#!/usr/bin/env bash
#
# validate_output.sh — Validate normalized prediction output directory
#
# Usage:
#   ./tests/validate_output.sh /path/to/output [--with-report]
#
# Checks:
#   - model_1.pdb exists and contains ATOM records
#   - model_1.cif exists and is non-empty
#   - confidence.json has required fields (plddt_mean, per_residue_plddt)
#   - metadata.json has required fields (tool, runtime_seconds)
#   - raw_output/ directory exists
#   - report.html exists, >10KB, valid HTML (only with --with-report)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0
WARNED=0

pass() {
    echo -e "  ${GREEN}PASS${NC}: $1"
    ((PASSED++))
}

fail() {
    echo -e "  ${RED}FAIL${NC}: $1"
    ((FAILED++))
}

warn() {
    echo -e "  ${YELLOW}WARN${NC}: $1"
    ((WARNED++))
}

# Parse arguments
OUTPUT_DIR=""
WITH_REPORT=false

for arg in "$@"; do
    case "$arg" in
        --with-report) WITH_REPORT=true ;;
        -*) echo "Unknown option: $arg"; exit 1 ;;
        *) OUTPUT_DIR="$arg" ;;
    esac
done

if [[ -z "$OUTPUT_DIR" ]]; then
    echo "Usage: $0 /path/to/output [--with-report]"
    exit 1
fi

if [[ ! -d "$OUTPUT_DIR" ]]; then
    echo "Error: Directory not found: $OUTPUT_DIR"
    exit 1
fi

echo "Validating output: $OUTPUT_DIR"
echo "=========================================="

# --- model_1.pdb ---
echo ""
echo "Structure files:"

if [[ -f "$OUTPUT_DIR/model_1.pdb" ]]; then
    pass "model_1.pdb exists"

    ATOM_COUNT=$(grep -c "^ATOM" "$OUTPUT_DIR/model_1.pdb" 2>/dev/null || echo "0")
    if [[ "$ATOM_COUNT" -gt 0 ]]; then
        pass "model_1.pdb contains $ATOM_COUNT ATOM records"
    else
        fail "model_1.pdb contains no ATOM records"
    fi

    FILE_SIZE=$(stat -c%s "$OUTPUT_DIR/model_1.pdb" 2>/dev/null || stat -f%z "$OUTPUT_DIR/model_1.pdb" 2>/dev/null || echo "0")
    if [[ "$FILE_SIZE" -gt 100 ]]; then
        pass "model_1.pdb size: ${FILE_SIZE} bytes"
    else
        fail "model_1.pdb too small: ${FILE_SIZE} bytes"
    fi
else
    fail "model_1.pdb not found"
fi

# --- model_1.cif ---
if [[ -f "$OUTPUT_DIR/model_1.cif" ]]; then
    pass "model_1.cif exists"

    FILE_SIZE=$(stat -c%s "$OUTPUT_DIR/model_1.cif" 2>/dev/null || stat -f%z "$OUTPUT_DIR/model_1.cif" 2>/dev/null || echo "0")
    if [[ "$FILE_SIZE" -gt 100 ]]; then
        pass "model_1.cif size: ${FILE_SIZE} bytes"
    else
        fail "model_1.cif too small: ${FILE_SIZE} bytes"
    fi
else
    fail "model_1.cif not found"
fi

# --- confidence.json ---
echo ""
echo "Confidence metrics:"

if [[ -f "$OUTPUT_DIR/confidence.json" ]]; then
    pass "confidence.json exists"

    # Check required fields using python (available in predict-structure env)
    if python3 -c "
import json, sys
data = json.load(open('$OUTPUT_DIR/confidence.json'))
assert 'plddt_mean' in data, 'missing plddt_mean'
assert 'per_residue_plddt' in data, 'missing per_residue_plddt'
assert isinstance(data['per_residue_plddt'], list), 'per_residue_plddt not a list'
assert len(data['per_residue_plddt']) > 0, 'per_residue_plddt is empty'
plddt = data['plddt_mean']
assert 0 <= plddt <= 100, f'plddt_mean out of range: {plddt}'
" 2>/dev/null; then
        PLDDT=$(python3 -c "import json; print(json.load(open('$OUTPUT_DIR/confidence.json'))['plddt_mean'])")
        RESIDUES=$(python3 -c "import json; print(len(json.load(open('$OUTPUT_DIR/confidence.json'))['per_residue_plddt']))")
        pass "confidence.json valid: pLDDT=${PLDDT}, ${RESIDUES} residues"
    else
        fail "confidence.json missing required fields or invalid values"
    fi

    # Optional PTM
    if python3 -c "
import json
data = json.load(open('$OUTPUT_DIR/confidence.json'))
assert data.get('ptm') is not None
" 2>/dev/null; then
        PTM=$(python3 -c "import json; print(json.load(open('$OUTPUT_DIR/confidence.json'))['ptm'])")
        pass "confidence.json has ptm: ${PTM}"
    else
        warn "confidence.json has no ptm (optional)"
    fi
else
    fail "confidence.json not found"
fi

# --- metadata.json ---
echo ""
echo "Metadata:"

if [[ -f "$OUTPUT_DIR/metadata.json" ]]; then
    pass "metadata.json exists"

    if python3 -c "
import json, sys
data = json.load(open('$OUTPUT_DIR/metadata.json'))
assert 'tool' in data, 'missing tool'
assert 'runtime_seconds' in data, 'missing runtime_seconds'
assert data['tool'] in ('boltz', 'chai', 'alphafold', 'esmfold'), f'unknown tool: {data[\"tool\"]}'
" 2>/dev/null; then
        TOOL=$(python3 -c "import json; print(json.load(open('$OUTPUT_DIR/metadata.json'))['tool'])")
        RUNTIME=$(python3 -c "import json; print(json.load(open('$OUTPUT_DIR/metadata.json'))['runtime_seconds'])")
        pass "metadata.json valid: tool=${TOOL}, runtime=${RUNTIME}s"
    else
        fail "metadata.json missing required fields"
    fi
else
    fail "metadata.json not found"
fi

# --- raw_output/ ---
echo ""
echo "Raw output:"

if [[ -d "$OUTPUT_DIR/raw_output" ]]; then
    pass "raw_output/ directory exists"

    RAW_FILES=$(find "$OUTPUT_DIR/raw_output" -type f | wc -l)
    if [[ "$RAW_FILES" -gt 0 ]]; then
        pass "raw_output/ contains $RAW_FILES file(s)"
    else
        warn "raw_output/ is empty"
    fi
else
    fail "raw_output/ directory not found"
fi

# --- report.html (optional, only with --with-report) ---
if $WITH_REPORT; then
    echo ""
    echo "Characterization report:"

    if [[ -f "$OUTPUT_DIR/report.html" ]] || [[ -f "$OUTPUT_DIR/report/report.html" ]]; then
        REPORT_PATH="$OUTPUT_DIR/report.html"
        [[ -f "$OUTPUT_DIR/report/report.html" ]] && REPORT_PATH="$OUTPUT_DIR/report/report.html"

        pass "report.html exists"

        FILE_SIZE=$(stat -c%s "$REPORT_PATH" 2>/dev/null || stat -f%z "$REPORT_PATH" 2>/dev/null || echo "0")
        if [[ "$FILE_SIZE" -gt 10240 ]]; then
            pass "report.html size: ${FILE_SIZE} bytes (>10KB)"
        else
            fail "report.html too small: ${FILE_SIZE} bytes (expected >10KB)"
        fi

        if grep -q "<html" "$REPORT_PATH" 2>/dev/null; then
            pass "report.html contains valid HTML"
        else
            fail "report.html does not appear to be valid HTML"
        fi
    else
        fail "report.html not found"
    fi
fi

# --- Summary ---
echo ""
echo "=========================================="
TOTAL=$((PASSED + FAILED))
echo -e "Results: ${GREEN}${PASSED} passed${NC}, ${RED}${FAILED} failed${NC}, ${YELLOW}${WARNED} warnings${NC} (${TOTAL} checks)"

if [[ "$FAILED" -gt 0 ]]; then
    echo -e "${RED}VALIDATION FAILED${NC}"
    exit 1
else
    echo -e "${GREEN}VALIDATION PASSED${NC}"
    exit 0
fi
