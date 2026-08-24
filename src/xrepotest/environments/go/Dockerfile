FROM golang:1.25-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV GOPATH=/go \
    GOBCO_PATH=/usr/local/gobco/bin \
    GOMUTESTING_PATH=/usr/local/gomutesting/bin \
    PATH=$PATH:/usr/local/gobco/bin:/usr/local/gomutesting/bin

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages --no-cache-dir \
    datasets \
    tree-sitter \
    tree-sitter-go

RUN mkdir -p "$GOBCO_PATH" "$GOMUTESTING_PATH" && \
    GOBIN="$GOBCO_PATH" go install github.com/rillig/gobco@latest && \
    GOBIN="$GOMUTESTING_PATH" go install github.com/avito-tech/go-mutesting/cmd/go-mutesting@latest && \
    go install golang.org/x/tools/cmd/goimports@latest

WORKDIR /app

# Copy repo data
COPY repo_data/go/ /app/repo_data/

# Copy shared xrepotest dataset and core logic
COPY src/xrepotest/__init__.py src/xrepotest/languages.py src/xrepotest/config.py src/xrepotest/paths.py /app/xrepotest/
COPY src/xrepotest/environments/xrepotest/ /app/xrepotest/

# Copy shared base logic
COPY src/xrepotest/environments/base/ /app/base/

# Copy Go specific files
COPY src/xrepotest/environments/go/ /app/go/

# Create main.py shim and set PYTHONPATH
RUN echo "from go.main import main; main()" > /app/main.py
ENV PYTHONPATH=/app

RUN for dir in /app/repo_data/*/; do \
    if [ -f "$dir/go.mod" ]; then \
        echo "Pre-fetching Go dependencies for $dir"; \
        cd "$dir" && go mod download || echo "Failed to download modules for $dir"; \
    fi; \
done

