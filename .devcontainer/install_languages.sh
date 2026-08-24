#!/usr/bin/env bash
# Optional language toolchain + LSP server installer for xrepotest.
#
# Only needed for DATA CONSTRUCTION work (crawler + LSP enrichment + RAG
# indexing over Go/Rust/Ruby/Julia/PHP source). Evaluation does NOT need this:
# `xrepotest eval` runs each language inside its own Docker container
# (tessera2025testgen/tessera:<lang>_environment), not in the devcontainer.
#
# Run manually inside the devcontainer when you need to (re)build data:
#   bash .devcontainer/install_languages.sh
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

cd /workspace

echo ""
info "================================================================"
info " xrepotest – language toolchain setup (data construction only)"
info "================================================================"
echo ""

# ── Go ────────────────────────────────────────────────────────────────────────
info "Setting up Go..."
if ! command -v go &>/dev/null; then
    GO_VERSION=1.21.13
    curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" -o /tmp/go.tar.gz
    sudo rm -rf /usr/local/go
    sudo tar -C /usr/local -xzf /tmp/go.tar.gz
    rm /tmp/go.tar.gz
    echo 'export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin' >> "$HOME/.bashrc"
    export PATH="$PATH:/usr/local/go/bin:$HOME/go/bin"
fi
if command -v go &>/dev/null; then
    go install golang.org/x/tools/gopls@latest
    success "Go ready: $(go version), gopls installed"
else
    warning "Go installation failed"
fi

# ── Rust ─────────────────────────────────────────────────────────────────────
info "Setting up Rust..."
if ! command -v rustup &>/dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain none
fi
# shellcheck disable=SC1090
source "$HOME/.cargo/env" 2>/dev/null || true
if command -v rustup &>/dev/null; then
    rustup toolchain install nightly
    rustup component add rust-analyzer 2>/dev/null || warning "rust-analyzer component unavailable via rustup"
    rustup component add llvm-tools-preview --toolchain nightly
    cargo install cargo-llvm-cov --locked --quiet
    rustup default nightly
    success "Rust toolchain ready (nightly + rust-analyzer + cargo-llvm-cov)"
else
    warning "rustup installation failed; skipping Rust toolchain setup"
fi

# ── Ruby (via rbenv) ─────────────────────────────────────────────────────────
info "Setting up Ruby..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends -qq \
    libssl-dev libyaml-dev libreadline6-dev zlib1g-dev libgmp-dev \
    libncurses5-dev libffi-dev libgdbm6 libgdbm-dev libdb-dev >/dev/null

if ! command -v rbenv &>/dev/null; then
    git clone --quiet https://github.com/rbenv/rbenv.git "$HOME/.rbenv"
    git clone --quiet https://github.com/rbenv/ruby-build.git "$HOME/.rbenv/plugins/ruby-build"
    {
        echo ''
        echo '# rbenv'
        echo 'export PATH="$HOME/.rbenv/bin:$PATH"'
        echo 'eval "$(rbenv init - bash)"'
    } >> "$HOME/.bashrc"
fi
export PATH="$HOME/.rbenv/bin:$PATH"
eval "$(rbenv init - bash)"

RUBY_VERSION=3.2.2
rbenv install -s "$RUBY_VERSION"
rbenv global "$RUBY_VERSION"
gem install bundler simplecov rspec solargraph --no-document --quiet
success "Ruby ready: $(ruby --version), gems installed (bundler, simplecov, rspec, solargraph)"

COMPOSER_BIN="$HOME/.composer/vendor/bin"
if ! grep -q "$COMPOSER_BIN" "$HOME/.bashrc" 2>/dev/null; then
    echo "" >> "$HOME/.bashrc"
    echo "# Composer global bin" >> "$HOME/.bashrc"
    echo "export PATH=\"$COMPOSER_BIN:\$PATH\"" >> "$HOME/.bashrc"
fi

# ── Julia ─────────────────────────────────────────────────────────────────────
info "Setting up Julia..."
if ! command -v julia &>/dev/null; then
    JULIA_VERSION=1.10.0
    curl -fsSL "https://julialang-s3.julialang.org/bin/linux/x64/1.10/julia-${JULIA_VERSION}-linux-x86_64.tar.gz" -o /tmp/julia.tar.gz
    sudo tar -xzf /tmp/julia.tar.gz -C /opt
    sudo ln -sf "/opt/julia-${JULIA_VERSION}/bin/julia" /usr/local/bin/julia
    rm /tmp/julia.tar.gz
fi
if command -v julia &>/dev/null; then
    julia -e 'using Pkg; Pkg.add(["LanguageServer", "SymbolServer"])' 2>/dev/null \
        && success "Julia ready: $(julia --version), LanguageServer/SymbolServer installed" \
        || warning "Julia package install failed (non-fatal)"
else
    warning "Julia installation failed"
fi

# ── PHP ───────────────────────────────────────────────────────────────────────
info "Setting up PHP..."
if ! command -v php &>/dev/null; then
    sudo apt-get install -y --no-install-recommends -qq \
        php php-cli php-common php-curl php-mbstring php-xml php-zip php-bcmath php-xdebug >/dev/null
fi
if command -v php &>/dev/null; then
    PHP_VERSION=$(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;')
    XDEBUG_CONF="/etc/php/${PHP_VERSION}/cli/conf.d/99-xdebug.ini"
    if [ -f "$XDEBUG_CONF" ] && ! grep -q "xdebug.mode" "$XDEBUG_CONF"; then
        echo "xdebug.mode=coverage" | sudo tee -a "$XDEBUG_CONF" >/dev/null
    fi
    if ! command -v composer &>/dev/null; then
        curl -sS https://getcomposer.org/installer \
            | php -- --install-dir=/usr/local/bin --filename=composer
    fi
    if ! command -v phpunit &>/dev/null; then
        sudo curl -fsSL -o /usr/local/bin/phpunit https://phar.phpunit.de/phpunit-9.phar
        sudo chmod +x /usr/local/bin/phpunit
    fi
    if command -v npm &>/dev/null; then
        npm install -g intelephense --silent
        success "PHP ready (PHP ${PHP_VERSION}, PHPUnit, Xdebug, Intelephense)"
    else
        success "PHP ready (PHP ${PHP_VERSION}, PHPUnit, Xdebug)"
        warning "npm not found; skipping Intelephense (PHP LSP) installation"
    fi
else
    warning "PHP installation failed"
fi

# ── Python extras for LSP enrichment / RAG indexing ──────────────────────────
info "Installing Python extras for LSP + RAG data construction..."
uv pip install -e ".[lsp,rag]"
success "Installed xrepotest[lsp,rag]"

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

_check go       "go version"
_check gopls    "gopls version"
_check rustc    "rustc --version"
_check ruby     "ruby --version"
_check solargraph "solargraph --version"
_check julia    "julia --version"
_check php      "php --version"
_check phpunit  "phpunit --version"
_check composer "composer --version"

echo ""
success "================================================================"
success " Language toolchain setup complete!"
success " Restart your shell (or run: source ~/.bashrc) to pick up PATH changes."
success "================================================================"
echo ""
