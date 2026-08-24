# Julia Evaluation Environment
FROM julia:1.10-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages --no-cache-dir \
    datasets \
    tree-sitter \
    tree-sitter-julia

# Install Julia packages for coverage
RUN julia -e 'using Pkg; Pkg.add(["Coverage", "JSON", "Test", "ArgParse"])'

WORKDIR /app

# Copy repo data
COPY repo_data/julia/ /app/repo_data/

# Copy shared xrepotest dataset and core logic
COPY src/xrepotest/__init__.py src/xrepotest/languages.py src/xrepotest/config.py src/xrepotest/paths.py /app/xrepotest/
COPY src/xrepotest/environments/xrepotest/ /app/xrepotest/

# Copy shared base logic
COPY src/xrepotest/environments/base/ /app/base/

# Copy Julia specific files into package structure
COPY src/xrepotest/environments/julia/ /app/julia/

# Copy Julia scripts to /app for absolute path compatibility
COPY src/xrepotest/environments/julia/*.jl /app/

# Create main.py shim and set PYTHONPATH
RUN echo "from julia.main import main; main()" > /app/main.py
ENV PYTHONPATH=/app

RUN for dir in /app/repo_data/*/; do \
    if [ -f "$dir/Project.toml" ]; then \
        echo "Pre-fetching Julia dependencies for $dir"; \
        julia --project="$dir" -e 'using Pkg; Pkg.instantiate()' || echo "Failed to instantiate for $dir"; \
    fi; \
done

CMD ["/bin/bash"]
