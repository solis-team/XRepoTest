# xrepotest unified dev container
#
# Evaluation-focused by default: Python only. Each evaluation language
# (Go/Rust/Julia/PHP/Ruby) runs inside its own Docker container
# (tessera2025testgen/tessera:<lang>_environment), not in this devcontainer.
#
# Data construction (crawler + LSP enrichment + RAG indexing) needs the
# actual language toolchains and LSP servers on the box. Install those on
# demand with: bash .devcontainer/install_languages.sh
FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

# ── System packages ──────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build tool (not in base image)
    pkg-config \
    # Full vim (base only has vim-tiny)
    vim \
    # Locale generation
    locales \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# ── uv package manager ──────────────────────────────────────────────────────
# Faster, cleaner replacement for pip. The Python interpreter itself is
# installed by the ghcr.io/devcontainers/features/python:1 feature (3.12),
# which also provides python3.12-dev and python3.12-venv — no need to
# install python3-dev or python3-venv here.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ── Workspace ────────────────────────────────────────────────────────────────
RUN mkdir -p /workspace \
    && chown -R ${USERNAME}:${USERNAME} /workspace

USER ${USERNAME}
WORKDIR /workspace

CMD ["/bin/bash"]
