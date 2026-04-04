#!/bin/bash
# GPU Acceptance Test Suite for PredictStructureApp
# Target: A100/H100/H200 GPU with Apptainer/Singularity
#
# MAIN FOCUS: Testing App-PredictStructure.pl - the BV-BRC service script
#
# Usage: ./gpu_acceptance_test.sh <container.sif> [options]
#
# Options:
#   --with-token <path>   Path to .patric_token for workspace tests
#   --quick               ESMFold only (fastest, ~30s)
#   --full                All 4 tools (hours on GPU)
#   --output-dir <path>   Directory for test outputs (default: ./gpu_test_output)
#
# Tests:
#   1. GPU detection (nvidia-smi, CUDA, memory)
#   2. Container integrity (all 4 tools + unified CLI)
#   3. Preflight validation (each tool, JSON output)
#   4. ESMFold prediction via App-PredictStructure.pl (~30s)
#   5. Output validation via validate_output.sh
#   6. Optional --full: all 4 tools

set -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

PASSED=0
FAILED=0
WARNED=0
SKIPPED=0

CONTAINER_PATH=""
TOKEN_PATH=""
QUICK_MODE=true
FULL_MODE=false
OUTPUT_DIR="./gpu_test_output"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DATA_DIR="$SCRIPT_DIR/../test_data"
LOG_FILE=""
START_TIME=""

pass() {
    echo -e "  ${GREEN}[PASS]${NC} $1"
    PASSED=$((PASSED + 1))
    echo "[PASS] $1" >> "$LOG_FILE"
}

fail() {
    echo -e "  ${RED}[FAIL]${NC} $1"
    FAILED=$((FAILED + 1))
    echo "[FAIL] $1" >> "$LOG_FILE"
}

warn() {
    echo -e "  ${YELLOW}[WARN]${NC} $1"
    WARNED=$((WARNED + 1))
    echo "[WARN] $1" >> "$LOG_FILE"
}

skip() {
    echo -e "  ${CYAN}[SKIP]${NC} $1"
    SKIPPED=$((SKIPPED + 1))
    echo "[SKIP] $1" >> "$LOG_FILE"
}

section() {
    echo ""
    echo -e "${BLUE}=== $1 ===${NC}"
    echo "" >> "$LOG_FILE"
    echo "=== $1 ===" >> "$LOG_FILE"
}

usage() {
    echo "Usage: $0 <container.sif> [options]"
    echo ""
    echo "Options:"
    echo "  --with-token <path>   Path to .patric_token for workspace tests"
    echo "  --quick               ESMFold only (default, ~30s)"
    echo "  --full                All 4 tools (hours on GPU)"
    echo "  --output-dir <path>   Test output directory (default: ./gpu_test_output)"
    echo "  --help                Show this help message"
    exit 1
}

# Parse arguments
parse_args() {
    if [ $# -eq 0 ]; then
        usage
    fi

    CONTAINER_PATH="$1"
    shift

    while [[ $# -gt 0 ]]; do
        case $1 in
            --with-token)
                TOKEN_PATH="$2"
                shift 2
                ;;
            --quick)
                QUICK_MODE=true
                FULL_MODE=false
                shift
                ;;
            --full)
                FULL_MODE=true
                QUICK_MODE=false
                shift
                ;;
            --output-dir)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            --help)
                usage
                ;;
            *)
                echo "Unknown option: $1"
                usage
                ;;
        esac
    done
}

detect_runtime() {
    if command -v apptainer &>/dev/null; then
        CONTAINER_CMD="apptainer"
    elif command -v singularity &>/dev/null; then
        CONTAINER_CMD="singularity"
    else
        fail "Neither singularity nor apptainer command found"
        exit 1
    fi
    pass "Container runtime: $CONTAINER_CMD"
}

setup_environment() {
    section "Setup"
    START_TIME=$(date +%s)
    mkdir -p "$OUTPUT_DIR"
    LOG_FILE="$OUTPUT_DIR/gpu_acceptance_results.log"

    echo "GPU Acceptance Test Results" > "$LOG_FILE"
    echo "Date: $(date)" >> "$LOG_FILE"
    echo "Container: $CONTAINER_PATH" >> "$LOG_FILE"
    echo "Mode: $([ "$FULL_MODE" = "true" ] && echo "full" || echo "quick")" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"

    echo "  Output: $OUTPUT_DIR"
    echo "  Log: $LOG_FILE"
    pass "Test environment initialized"
}

# ================================================================
# Test 1: GPU access
# ================================================================
test_gpu_access() {
    section "GPU Access"

    if $CONTAINER_CMD exec --nv "$CONTAINER_PATH" nvidia-smi &>/dev/null; then
        pass "nvidia-smi accessible in container"

        GPU_INFO=$($CONTAINER_CMD exec --nv "$CONTAINER_PATH" nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)
        echo "    GPU: $GPU_INFO"

        # Check GPU type
        if echo "$GPU_INFO" | grep -qiE "H100|H200"; then
            pass "High-end GPU detected: $GPU_INFO"
        elif echo "$GPU_INFO" | grep -qi "A100"; then
            pass "A100 GPU detected"
        else
            warn "Unexpected GPU: $GPU_INFO (expected A100/H100/H200)"
        fi

        # Check GPU memory
        GPU_MEM=$($CONTAINER_CMD exec --nv "$CONTAINER_PATH" nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d '[:space:]')
        if [ "${GPU_MEM:-0}" -ge 40000 ]; then
            pass "GPU memory sufficient: ${GPU_MEM}MB"
        else
            warn "GPU memory: ${GPU_MEM}MB (40GB+ recommended)"
        fi
    else
        fail "nvidia-smi not accessible (no GPU or --nv not working)"
        return 1
    fi

    # Test PyTorch CUDA
    if $CONTAINER_CMD exec --nv "$CONTAINER_PATH" python3 -c "import torch; assert torch.cuda.is_available()" &>/dev/null; then
        CUDA_VERSION=$($CONTAINER_CMD exec --nv "$CONTAINER_PATH" python3 -c "import torch; print(torch.version.cuda)" 2>/dev/null)
        pass "PyTorch CUDA functional: CUDA $CUDA_VERSION"
    else
        fail "PyTorch CUDA not functional"
    fi
}

# ================================================================
# Test 2: Container integrity
# ================================================================
test_container_integrity() {
    section "Container Integrity"

    if [ ! -f "$CONTAINER_PATH" ]; then
        fail "Container file not found: $CONTAINER_PATH"
        return 1
    fi

    CONTAINER_SIZE=$(du -h "$CONTAINER_PATH" | cut -f1)
    pass "Container file: $CONTAINER_SIZE"

    # Unified CLI
    if $CONTAINER_CMD exec "$CONTAINER_PATH" predict-structure --version &>/dev/null; then
        pass "predict-structure CLI"
    else
        fail "predict-structure CLI not available"
    fi

    # Individual tools
    for tool_check in "boltz:boltz --help" "chai:chai --help" "esmfold:esm-fold-hf --help"; do
        local name="${tool_check%%:*}"
        local cmd="${tool_check#*:}"
        if $CONTAINER_CMD exec "$CONTAINER_PATH" $cmd &>/dev/null; then
            pass "$name CLI"
        else
            warn "$name CLI not available"
        fi
    done

    # Service script
    if $CONTAINER_CMD exec "$CONTAINER_PATH" perl -c /kb/module/service-scripts/App-PredictStructure.pl &>/dev/null; then
        pass "Service script syntax: OK"
    else
        fail "Service script syntax check failed"
    fi

    # App spec
    if $CONTAINER_CMD exec "$CONTAINER_PATH" python3 -c "import json; json.load(open('/kb/module/app_specs/PredictStructure.json'))" &>/dev/null; then
        pass "App spec valid JSON"
    else
        fail "App spec invalid"
    fi
}

# ================================================================
# Test 3: Preflight validation
# ================================================================
test_preflight() {
    section "Preflight Validation"

    for tool in esmfold boltz chai alphafold; do
        local output
        output=$($CONTAINER_CMD exec "$CONTAINER_PATH" predict-structure preflight --tool "$tool" 2>/dev/null)

        if echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert data['resolved_tool'] == '$tool'
assert 'cpu' in data and 'memory' in data and 'runtime' in data
sys.exit(0)
" 2>/dev/null; then
            local gpu=$(echo "$output" | python3 -c "import json,sys; print(json.load(sys.stdin)['needs_gpu'])" 2>/dev/null)
            local mem=$(echo "$output" | python3 -c "import json,sys; print(json.load(sys.stdin)['memory'])" 2>/dev/null)
            local rt=$(echo "$output" | python3 -c "import json,sys; print(json.load(sys.stdin)['runtime'])" 2>/dev/null)
            pass "Preflight $tool: gpu=$gpu mem=$mem runtime=${rt}s"
        else
            fail "Preflight $tool: invalid output"
        fi
    done
}

# ================================================================
# Test 4+5: Prediction via App-PredictStructure.pl + output validation
# ================================================================
run_service_test() {
    local tool=$1
    local params_file=$2
    local test_name="service_${tool}"
    local test_output="$OUTPUT_DIR/$test_name"

    echo ""
    echo -e "  ${CYAN}Running App-PredictStructure.pl: $tool${NC}"

    mkdir -p "$test_output"

    local pred_start=$(date +%s)

    if $CONTAINER_CMD exec --nv \
        -B "$TEST_DATA_DIR:/data:ro" \
        -B "$test_output:/output" \
        -B "$params_file:/params.json:ro" \
        --env TMPDIR=/tmp \
        --env P3_WORKDIR=/output \
        "$CONTAINER_PATH" \
        perl /kb/module/service-scripts/App-PredictStructure.pl \
            "http://localhost" \
            /kb/module/app_specs/PredictStructure.json \
            /params.json \
        2>&1 | tee "$test_output/service.log"; then

        local pred_end=$(date +%s)
        local pred_time=$((pred_end - pred_start))

        pass "$test_name completed (${pred_time}s)"
        echo "[TIMING] $test_name: ${pred_time}s" >> "$LOG_FILE"

        # Find the output directory (service creates a timestamped subfolder)
        local result_dir
        result_dir=$(find "$test_output/output" -maxdepth 1 -type d -name "predict_structure_result_*" 2>/dev/null | head -1)
        if [ -z "$result_dir" ]; then
            result_dir="$test_output/output"
        fi

        # Run output validation
        if [ -x "$SCRIPT_DIR/validate_output.sh" ]; then
            echo ""
            echo "  Validating output..."
            if "$SCRIPT_DIR/validate_output.sh" "$result_dir" 2>/dev/null; then
                pass "$test_name output validation"
            else
                fail "$test_name output validation"
            fi
        else
            warn "validate_output.sh not found, skipping output validation"
        fi
    else
        fail "$test_name failed"
        echo "  Check log: $test_output/service.log"
    fi
}

test_predictions() {
    section "Prediction Tests (App-PredictStructure.pl)"

    # Check test data
    if [ ! -d "$TEST_DATA_DIR" ]; then
        fail "Test data directory not found: $TEST_DATA_DIR"
        return 1
    fi

    # ESMFold (always run — fast, ~30s)
    if [ -f "$TEST_DATA_DIR/params_esmfold.json" ]; then
        run_service_test "esmfold" "$TEST_DATA_DIR/params_esmfold.json"
    else
        fail "Test params missing: params_esmfold.json"
    fi

    # Full mode: run all tools
    if [ "$FULL_MODE" = "true" ]; then
        echo ""
        echo -e "  ${CYAN}Full mode: testing all tools${NC}"

        if [ -f "$TEST_DATA_DIR/params_boltz.json" ]; then
            run_service_test "boltz" "$TEST_DATA_DIR/params_boltz.json"
        fi

        # Chai (similar params to boltz)
        local chai_params="$OUTPUT_DIR/params_chai.json"
        cat > "$chai_params" << 'EOF'
{
    "tool": "chai",
    "input_file": "/data/simple_protein.fasta",
    "output_path": "/output",
    "num_samples": 1,
    "num_recycles": 3,
    "sampling_steps": 200,
    "output_format": "pdb",
    "msa_mode": "server",
    "seed": 42
}
EOF
        run_service_test "chai" "$chai_params"

        # AlphaFold
        local af2_params="$OUTPUT_DIR/params_alphafold.json"
        cat > "$af2_params" << 'EOF'
{
    "tool": "alphafold",
    "input_file": "/data/simple_protein.fasta",
    "output_path": "/output",
    "num_recycles": 3,
    "output_format": "pdb",
    "msa_mode": "none",
    "af2_data_dir": "/databases",
    "af2_model_preset": "monomer",
    "af2_db_preset": "reduced_dbs",
    "seed": 42
}
EOF
        run_service_test "alphafold" "$af2_params"
    else
        skip "Boltz prediction (use --full)"
        skip "Chai prediction (use --full)"
        skip "AlphaFold prediction (use --full)"
    fi
}

# ================================================================
# Workspace connectivity (optional)
# ================================================================
test_workspace() {
    section "Workspace Connectivity"

    if [ -z "$TOKEN_PATH" ]; then
        skip "Workspace tests (use --with-token)"
        return 0
    fi

    if [ ! -f "$TOKEN_PATH" ]; then
        fail "Token file not found: $TOKEN_PATH"
        return 1
    fi
    pass "Token file exists"

    AUTH_TOKEN=$(cat "$TOKEN_PATH")

    local ws_result
    ws_result=$($CONTAINER_CMD exec \
        --env P3_AUTH_TOKEN="$AUTH_TOKEN" \
        "$CONTAINER_PATH" \
        perl -e '
use strict;
use warnings;
use Bio::P3::Workspace::WorkspaceClientExt;

eval {
    my $ws = Bio::P3::Workspace::WorkspaceClientExt->new();
    print "SUCCESS\n";
};
if ($@) {
    print "ERROR: $@\n";
    exit 1;
}
' 2>&1 || true)

    if echo "$ws_result" | grep -q "SUCCESS"; then
        pass "Workspace client initialization"
    else
        warn "Workspace client: $ws_result"
    fi
}

# ================================================================
# Summary
# ================================================================
generate_report() {
    section "Summary"

    local end_time=$(date +%s)
    local total_time=$((end_time - START_TIME))

    local total=$((PASSED + FAILED + WARNED + SKIPPED))

    echo ""
    echo "================================================"
    echo "  GPU ACCEPTANCE TEST RESULTS"
    echo "================================================"
    echo -e "  ${GREEN}Passed:  $PASSED${NC}"
    [ $FAILED -gt 0 ] && echo -e "  ${RED}Failed:  $FAILED${NC}"
    [ $WARNED -gt 0 ] && echo -e "  ${YELLOW}Warned:  $WARNED${NC}"
    [ $SKIPPED -gt 0 ] && echo -e "  ${CYAN}Skipped: $SKIPPED${NC}"
    echo "  Total:   $total"
    echo "  Runtime: ${total_time}s"
    echo "================================================"

    echo "" >> "$LOG_FILE"
    echo "SUMMARY: passed=$PASSED failed=$FAILED warned=$WARNED skipped=$SKIPPED runtime=${total_time}s" >> "$LOG_FILE"

    echo ""
    echo "  Log: $LOG_FILE"

    if [ $FAILED -eq 0 ]; then
        echo -e "  ${GREEN}All critical tests passed!${NC}"
        return 0
    else
        echo -e "  ${RED}Some tests failed. Review log for details.${NC}"
        return 1
    fi
}

# ================================================================
# Main
# ================================================================
main() {
    parse_args "$@"

    echo ""
    echo "================================================"
    echo "  PredictStructureApp GPU Acceptance Test"
    echo "================================================"
    echo "  Container: $CONTAINER_PATH"
    echo "  Mode: $([ "$FULL_MODE" = "true" ] && echo "full (all 4 tools)" || echo "quick (ESMFold only)")"
    [ -n "$TOKEN_PATH" ] && echo "  Token: $TOKEN_PATH"
    echo "================================================"

    setup_environment
    detect_runtime
    test_gpu_access
    test_container_integrity
    test_preflight
    test_predictions
    test_workspace
    generate_report

    exit $?
}

main "$@"
