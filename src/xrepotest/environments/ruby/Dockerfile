# Enhanced Ruby Test Evaluation Environment
# Includes: RSpec, SimpleCov (coverage), Mutant (mutation testing), Tree-sitter
FROM ruby:3.2-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV RUBY_VERSION=3.2
ENV BUNDLE_SILENCE_ROOT_WARNING=1
ENV COVERAGE=true

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    python3 \
    python3-pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install both the latest and the 2.x series of Bundler to support older repos
RUN gem install --no-document bundler:2.4.22 bundler rspec simplecov mutant mutant-rspec

RUN pip3 install --break-system-packages --no-cache-dir \
    pyyaml \
    tree-sitter \
    tree-sitter-ruby

WORKDIR /app

# Copy repo data
COPY repo_data/ruby/ /app/repo_data/

# Copy shared xrepotest dataset and core logic
COPY src/xrepotest/__init__.py src/xrepotest/languages.py src/xrepotest/config.py src/xrepotest/paths.py /app/xrepotest/
COPY src/xrepotest/environments/xrepotest/ /app/xrepotest/

# Copy shared base logic
COPY src/xrepotest/environments/base/ /app/base/

# Copy Ruby specific files
COPY src/xrepotest/environments/ruby/ /app/ruby/

# Create main.py shim and set PYTHONPATH
RUN echo "from ruby.main import main; main()" > /app/main.py
ENV PYTHONPATH=/app

# Install isolated dependencies for each repo
# 1. Configures local vendor/bundle
# 2. Automatically uses the Bundler version specified in Gemfile.lock
RUN for dir in /app/repo_data/*/; do \
    if [ -f "$dir/Gemfile" ]; then \
        echo "Installing isolated dependencies for $dir"; \
        cd "$dir" && \
        bundle config set --local path 'vendor/bundle' && \
        bundle config set --local forget_cli_options true && \
        (bundle install --jobs=4 --retry=3 || bundle _2.4.22_ install --jobs=4 --retry=3 || echo "Failed to install gems for $dir"); \
    fi; \
done

RUN ruby --version && \
    gem --version && \
    bundler --version && \
    rspec --version && \
    mutant --version

CMD ["/bin/bash"]
