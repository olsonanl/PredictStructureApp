#!/bin/bash
# Apptainer/Singularity Container Validation Test for PredictStructureApp
#
# Usage: ./test_apptainer_container.sh <container.sif> [--with-token token_path]
#
# Tests:
# - All 4 tool CLIs + unified predict-structure CLI
# - Perl module loading (AppScript, Workspace, JSON, Try::Tiny, etc.)
# - Service script syntax check (perl -c)
# - App spec validation (valid JSON, correct script name)
# - Preflight test with params for each tool
# - Environment variables and directory structure
# - Optional workspace connectivity (--with-token)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASSED=0
FAILED=0
WARNED=0

pass() {
    echo -e "  ${GREEN}[PASS]${NC} $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo -e "  ${RED}[FAIL]${NC} $1"
    FAILED=$((FAILED + 1))
}

warn() {
    echo -e "  ${YELLOW}[WARN]${NC} $1"
    WARNED=$((WARNED + 1))
}

section() {
    echo ""
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Parse arguments
if [ -z "$1" ]; then
    echo "Usage: $0 <container.sif> [--with-token token_path]"
    exit 1
fi

CONTAINER_PATH="$1"
TOKEN_PATH=""
shift

while [[ $# -gt 0 ]]; do
    case $1 in
        --with-token)
            TOKEN_PATH="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "================================================"
echo "  PredictStructureApp Container Validation Test  "
echo "================================================"
echo "Container: $CONTAINER_PATH"
[ -n "$TOKEN_PATH" ] && echo "Token: $TOKEN_PATH"
echo "================================================"

# Detect container runtime
if command -v apptainer &>/dev/null; then
    CONTAINER_CMD="apptainer"
elif command -v singularity &>/dev/null; then
    CONTAINER_CMD="singularity"
else
    fail "Neither singularity nor apptainer command found"
    exit 1
fi
pass "Container runtime: $CONTAINER_CMD"

# ================================================================
# Container file
# ================================================================
section "Container File"

if [ -f "$CONTAINER_PATH" ]; then
    pass "Container file exists: $CONTAINER_PATH"
    CONTAINER_SIZE=$(du -h "$CONTAINER_PATH" | cut -f1)
    echo "    Size: $CONTAINER_SIZE"
else
    fail "Container file not found: $CONTAINER_PATH"
    exit 1
fi

# ================================================================
# Tool CLIs
# ================================================================
section "Tool CLIs"

# Unified CLI
if $CONTAINER_CMD exec "$CONTAINER_PATH" predict-structure --version &>/dev/null; then
    VERSION=$($CONTAINER_CMD exec "$CONTAINER_PATH" predict-structure --version 2>&1 | head -1)
    pass "predict-structure CLI: $VERSION"
else
    fail "predict-structure CLI not available"
fi

# Boltz
if $CONTAINER_CMD exec "$CONTAINER_PATH" boltz --help &>/dev/null; then
    pass "boltz CLI available"
else
    warn "boltz CLI not available"
fi

# Chai
if $CONTAINER_CMD exec "$CONTAINER_PATH" chai --help &>/dev/null; then
    pass "chai CLI available"
else
    warn "chai CLI not available"
fi

# AlphaFold (run_alphafold.py or alphafold command)
if $CONTAINER_CMD exec "$CONTAINER_PATH" bash -c "which run_alphafold.py 2>/dev/null || test -f /app/alphafold/run_alphafold.py" &>/dev/null; then
    pass "AlphaFold available"
else
    warn "AlphaFold not available"
fi

# ESMFold
if $CONTAINER_CMD exec "$CONTAINER_PATH" esm-fold-hf --help &>/dev/null; then
    pass "esm-fold-hf CLI available"
else
    warn "esm-fold-hf CLI not available"
fi

# ================================================================
# Perl
# ================================================================
section "Perl Runtime"

if PERL_VERSION=$($CONTAINER_CMD exec "$CONTAINER_PATH" perl -v 2>&1 | grep -o 'v[0-9]\+\.[0-9]\+\.[0-9]\+' | head -1); then
    pass "Perl available: $PERL_VERSION"
else
    fail "Perl not available"
fi

# Required Perl modules
section "Perl Modules"

test_perl_module() {
    local module=$1
    local required=${2:-true}
    if $CONTAINER_CMD exec "$CONTAINER_PATH" perl -e "use $module; print 'OK'" &>/dev/null; then
        pass "Module: $module"
    elif [ "$required" = "true" ]; then
        fail "Module: $module (failed to load)"
    else
        warn "Module: $module (optional, not available)"
    fi
}

# Core modules
test_perl_module "JSON"
test_perl_module "Try::Tiny"
test_perl_module "File::Slurp"
test_perl_module "File::Copy"
test_perl_module "File::Path"
test_perl_module "File::Basename"
test_perl_module "Carp::Always"
test_perl_module "Data::Dumper"
test_perl_module "POSIX"
test_perl_module "Getopt::Long"

# BV-BRC modules
test_perl_module "Bio::KBase::AppService::AppScript" "false"
test_perl_module "Bio::P3::Workspace::WorkspaceClient" "false"
test_perl_module "Bio::P3::Workspace::WorkspaceClientExt" "false"
test_perl_module "P3AuthToken" "false"

# ================================================================
# Service script
# ================================================================
section "Service Script"

SCRIPT_PATH="/kb/module/service-scripts/App-PredictStructure.pl"

if $CONTAINER_CMD exec "$CONTAINER_PATH" test -f "$SCRIPT_PATH"; then
    pass "Service script exists: $SCRIPT_PATH"
else
    fail "Service script missing: $SCRIPT_PATH"
fi

# Syntax check
if $CONTAINER_CMD exec "$CONTAINER_PATH" perl -c "$SCRIPT_PATH" &>/dev/null; then
    pass "Service script syntax: OK"
else
    fail "Service script syntax check failed"
    $CONTAINER_CMD exec "$CONTAINER_PATH" perl -c "$SCRIPT_PATH" 2>&1 | head -5
fi

# ================================================================
# App spec
# ================================================================
section "App Spec"

APP_SPEC="/kb/module/app_specs/PredictStructure.json"

if $CONTAINER_CMD exec "$CONTAINER_PATH" test -f "$APP_SPEC"; then
    pass "App spec exists: $APP_SPEC"
else
    fail "App spec missing: $APP_SPEC"
fi

# Validate JSON
if $CONTAINER_CMD exec "$CONTAINER_PATH" python3 -c "
import json, sys
data = json.load(open('$APP_SPEC'))
assert data.get('id') == 'PredictStructure', f'wrong id: {data.get(\"id\")}'
assert data.get('script') == 'App-PredictStructure', f'wrong script: {data.get(\"script\")}'
assert 'parameters' in data, 'missing parameters'
print('OK')
" &>/dev/null; then
    pass "App spec valid JSON with correct id/script"
else
    fail "App spec validation failed"
fi

# Check that all tools are in the enum
if $CONTAINER_CMD exec "$CONTAINER_PATH" python3 -c "
import json
data = json.load(open('$APP_SPEC'))
tool_param = next(p for p in data['parameters'] if p['id'] == 'tool')
expected = {'auto', 'boltz', 'chai', 'alphafold', 'esmfold'}
actual = set(tool_param['enum'])
assert actual == expected, f'tool enum mismatch: {actual} != {expected}'
print('OK')
" &>/dev/null; then
    pass "App spec tool enum: auto, boltz, chai, alphafold, esmfold"
else
    fail "App spec tool enum incomplete"
fi

# ================================================================
# Preflight tests
# ================================================================
section "Preflight Tests"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DATA_DIR="$SCRIPT_DIR/../test_data"

test_preflight() {
    local tool=$1
    local expected_gpu=$2  # "true" or "false"

    if $CONTAINER_CMD exec "$CONTAINER_PATH" predict-structure preflight --tool "$tool" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert data['resolved_tool'] == '$tool', f'wrong tool: {data[\"resolved_tool\"]}'
assert 'cpu' in data, 'missing cpu'
assert 'memory' in data, 'missing memory'
assert 'runtime' in data, 'missing runtime'
gpu = str(data['needs_gpu']).lower()
assert gpu == '$expected_gpu', f'needs_gpu: {gpu} != $expected_gpu'
print('OK')
" 2>/dev/null; then
        pass "Preflight $tool: needs_gpu=$expected_gpu"
    else
        fail "Preflight $tool failed"
    fi
}

test_preflight "esmfold" "false"
test_preflight "boltz" "true"
test_preflight "chai" "true"
test_preflight "alphafold" "true"

# ================================================================
# Environment variables
# ================================================================
section "Environment Variables"

ENV_VARS=(
    "PERL5LIB"
    "KB_TOP"
    "KB_DEPLOYMENT"
    "KB_MODULE_DIR"
    "IN_BVBRC_CONTAINER"
)

for var in "${ENV_VARS[@]}"; do
    if $CONTAINER_CMD exec "$CONTAINER_PATH" bash -c "[ -n \"\$$var\" ]" &>/dev/null; then
        VALUE=$($CONTAINER_CMD exec "$CONTAINER_PATH" bash -c "echo \$$var" 2>/dev/null)
        pass "Env: $var=$VALUE"
    else
        fail "Env not set: $var"
    fi
done

# ================================================================
# Directory structure
# ================================================================
section "Directory Structure"

DIRS=(
    "/kb/module"
    "/kb/module/service-scripts"
    "/kb/module/app_specs"
)

for dir in "${DIRS[@]}"; do
    if $CONTAINER_CMD exec "$CONTAINER_PATH" test -d "$dir"; then
        pass "Directory: $dir"
    else
        fail "Directory missing: $dir"
    fi
done

# ================================================================
# Python environment
# ================================================================
section "Python Environment"

if $CONTAINER_CMD exec "$CONTAINER_PATH" python3 -c "import predict_structure; print(predict_structure.__version__)" &>/dev/null; then
    PY_VERSION=$($CONTAINER_CMD exec "$CONTAINER_PATH" python3 -c "import predict_structure; print(predict_structure.__version__)" 2>/dev/null)
    pass "predict_structure Python package: v$PY_VERSION"
else
    fail "predict_structure Python package not importable"
fi

# Check protein_compare (optional)
if $CONTAINER_CMD exec "$CONTAINER_PATH" python3 -c "import protein_compare" &>/dev/null; then
    pass "protein_compare package available (report generation)"
else
    warn "protein_compare package not available (report generation disabled)"
fi

# ================================================================
# Workspace tests (optional)
# ================================================================
if [ -n "$TOKEN_PATH" ]; then
    section "Workspace Connectivity"

    if [ -f "$TOKEN_PATH" ]; then
        pass "Token file found: $TOKEN_PATH"

        AUTH_TOKEN=$(cat "$TOKEN_PATH")
        ws_result=$($CONTAINER_CMD exec \
            --env P3_AUTH_TOKEN="$AUTH_TOKEN" \
            "$CONTAINER_PATH" \
            perl -e '
use strict;
use warnings;
use Bio::P3::Workspace::WorkspaceClientExt;

eval {
    my $ws = Bio::P3::Workspace::WorkspaceClientExt->new();
    print "SUCCESS: Workspace client initialized\n";
};
if ($@) {
    print "ERROR: $@\n";
    exit 1;
}
' 2>&1 || true)

        if echo "$ws_result" | grep -q "SUCCESS"; then
            pass "Workspace client initialization"
        else
            warn "Workspace client failed: $ws_result"
        fi
    else
        fail "Token file not found: $TOKEN_PATH"
    fi
fi

# ================================================================
# Summary
# ================================================================
echo ""
echo "================================================"
echo "  Test Summary"
echo "================================================"
echo -e "  ${GREEN}Passed:  $PASSED${NC}"
if [ $FAILED -gt 0 ]; then
    echo -e "  ${RED}Failed:  $FAILED${NC}"
fi
if [ $WARNED -gt 0 ]; then
    echo -e "  ${YELLOW}Warned:  $WARNED${NC}"
fi
echo "================================================"

if [ $FAILED -eq 0 ]; then
    echo -e "  ${GREEN}All critical tests passed!${NC}"
    exit 0
else
    echo -e "  ${RED}Some tests failed!${NC}"
    exit 1
fi
