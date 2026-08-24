#!/usr/bin/env bash
# Pulls the xrepotest evaluation Docker images.
#
# Each language runs its evaluation in its own Docker container, image
# dungxg502/xrepotest-<lang>:latest. Requires Docker to be running.
#
# Usage:
#   bash .devcontainer/pull_images.sh            # pull all supported languages
#   bash .devcontainer/pull_images.sh go rust     # pull only the languages listed
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC}   $1"; }

IMAGE_PREFIX="dungxg502/xrepotest"
ALL_LANGUAGES=(go rust julia php ruby)

if [ "$#" -gt 0 ]; then
    LANGUAGES=("$@")
else
    LANGUAGES=("${ALL_LANGUAGES[@]}")
fi

if ! command -v docker &>/dev/null; then
    error "Docker not found. Docker must be installed and running to pull evaluation images."
    exit 1
fi

echo ""
info "================================================================"
info " xrepotest – pulling evaluation Docker images"
info "================================================================"
echo ""

FAILED=()
for lang in "${LANGUAGES[@]}"; do
    lang_lc=$(echo "$lang" | tr '[:upper:]' '[:lower:]')
    valid=false
    for supported in "${ALL_LANGUAGES[@]}"; do
        if [ "$lang_lc" == "$supported" ]; then
            valid=true
            break
        fi
    done
    if [ "$valid" != true ]; then
        warning "Skipping unsupported language: $lang (supported: ${ALL_LANGUAGES[*]})"
        continue
    fi

    image="${IMAGE_PREFIX}-${lang_lc}:latest"
    info "Pulling ${image}..."
    if docker pull "$image"; then
        success "Pulled ${image}"
    else
        error "Failed to pull ${image}"
        FAILED+=("$image")
    fi
done

echo ""
if [ "${#FAILED[@]}" -eq 0 ]; then
    success "================================================================"
    success " All requested images pulled successfully!"
    success "================================================================"
else
    error "================================================================"
    error " Some images failed to pull:"
    for img in "${FAILED[@]}"; do
        error "  - $img"
    done
    error "================================================================"
    exit 1
fi
echo ""
