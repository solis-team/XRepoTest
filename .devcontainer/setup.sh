#!/usr/bin/env bash
# Post-create setup for the xrepotest dev container.
#
# Evaluation-focused: installs Python only. Evaluation runs each language
# inside its own Docker container (dungxg502/xrepotest-<lang>:latest), pulled by
# pull_images.sh), so Go/Rust/Ruby/Julia/PHP toolchains aren't needed here.
#
# Building data (crawler + LSP enrichment + RAG indexing) needs those language
# toolchains and the xrepotest[lsp,rag] extras. Install them separately with:
#   bash .devcontainer/install_languages.sh
set -e

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

cd /workspace

echo ""
info "================================================================"
info " xrepotest – post-create environment setup"
info "================================================================"
echo ""

# ── Git ───────────────────────────────────────────────────────────────────────
info "Configuring Git..."
git config --global --add safe.directory '*' 2>/dev/null || true
success "Git configured"

# ── Python ───────────────────────────────────────────────────────────────────
info "Setting up Python environment..."
if [ -f "pyproject.toml" ]; then
    uv pip install -e ".[dev]"
    success "Installed xrepotest in editable mode (with dev extras)"
else
    warning "pyproject.toml not found; skipping editable install"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
info "================================================================"
info " Installation summary"
info "================================================================"
printf "%-20s %s\n" "Tool" "Version"
printf "%-20s %s\n" "----" "-------"

_check() {
    local tool=$1; local vcmd=$2
    if command -v "$tool" &>/dev/null; then
        printf "%-20s ${GREEN}%s${NC}\n" "$tool" "$(eval "$vcmd" 2>&1 | head -n1)"
    else
        printf "%-20s ${RED}%s${NC}\n" "$tool" "not found"
    fi
}

_check python "python --version"
_check docker "docker --version"

echo ""
success "================================================================"
success " Post-create setup complete!"
success ""
success " Need Go/Rust/Ruby/Julia/PHP toolchains for data construction?"
success " Run: bash .devcontainer/install_languages.sh"
success "================================================================"
echo ""
