FROM rust:1.83-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages --no-cache-dir \
    datasets \
    tree-sitter \
    tree-sitter-rust

# Install specific nightly version
RUN rustup toolchain install nightly-2025-11-22 && \
    rustup default nightly-2025-11-22

RUN curl -L https://github.com/cargo-bins/cargo-binstall/releases/latest/download/cargo-binstall-x86_64-unknown-linux-musl.tgz | tar -xvzf - -C /usr/local/bin && \
    cargo binstall -y cargo-llvm-cov && \
    cargo install cargo-mutants

WORKDIR /app

# Copy repo data
COPY repo_data/rust/ /app/repo_data/

# Copy shared xrepotest dataset and core logic
COPY src/xrepotest/__init__.py src/xrepotest/languages.py src/xrepotest/config.py src/xrepotest/paths.py /app/xrepotest/
COPY src/xrepotest/environments/xrepotest/ /app/xrepotest/

# Copy shared base logic
COPY src/xrepotest/environments/base/ /app/base/

# Copy Rust specific files
COPY src/xrepotest/environments/rust/ /app/rust/

# Create main.py shim and set PYTHONPATH
RUN echo "from rust.main import main; main()" > /app/main.py
ENV PYTHONPATH=/app

RUN for dir in /app/repo_data/*/; do \
    if [ -f "$dir/Cargo.toml" ]; then \
        echo "Pre-fetching Rust dependencies for $dir"; \
        cd "$dir" && cargo fetch || echo "Failed to fetch dependencies for $dir"; \
    fi; \
done
