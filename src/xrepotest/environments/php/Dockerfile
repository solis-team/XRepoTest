# Enhanced PHP Test Evaluation Environment
# Includes: PHPUnit, Xdebug (coverage), Tree-sitter
FROM php:8.2-cli-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV COMPOSER_ALLOW_SUPERUSER=1
ENV PATH="/root/.config/composer/vendor/bin:/root/.composer/vendor/bin:${PATH}"
ENV PHP_VERSION=8.2
ENV XDEBUG_MODE=coverage

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    curl \
    git \
    libicu-dev \
    libonig-dev \
    libxml2-dev \
    libzip-dev \
    libssl-dev \
    libpq-dev \
    python3 \
    python3-pip \
    unzip \
    ${PHPIZE_DEPS} \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN docker-php-ext-install intl zip ftp bcmath mbstring pcntl pdo_pgsql pgsql && \
    pecl install xdebug mongodb && \
    docker-php-ext-enable xdebug mongodb

RUN { \
    echo "xdebug.mode=coverage"; \
    echo "xdebug.start_with_request=no"; \
    echo "memory_limit=512M"; \
} > /usr/local/etc/php/conf.d/99-xrepotest.ini

RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer && \
    composer --version

RUN pip3 install --break-system-packages --no-cache-dir \
    tree-sitter \
    tree-sitter-php

WORKDIR /app

# Copy repo data
COPY repo_data/php/ /app/repo_data/

# Copy shared xrepotest dataset and core logic
COPY src/xrepotest/__init__.py src/xrepotest/languages.py src/xrepotest/config.py src/xrepotest/paths.py /app/xrepotest/
COPY src/xrepotest/environments/xrepotest/ /app/xrepotest/

# Copy shared base logic
COPY src/xrepotest/environments/base/ /app/base/

# Copy PHP specific files
COPY src/xrepotest/environments/php/ /app/php/

# Create main.py shim and set PYTHONPATH
RUN echo "from php.main import main; main()" > /app/main.py
ENV PYTHONPATH=/app

RUN for dir in /app/repo_data/*/; do \
    if [ -f "$dir/composer.json" ]; then \
        echo "Installing isolated dependencies for $dir"; \
        cd "$dir" && \
        (composer install --no-interaction --prefer-dist --optimize-autoloader --ignore-platform-reqs || \
         composer update --no-interaction --prefer-dist --optimize-autoloader --ignore-platform-reqs || \
         echo "Failed to install for $dir"); \
    fi; \
done

RUN php --version && \
    php -m | grep -i xdebug && \
    composer --version && \
    python3 -c "import tree_sitter; print('tree-sitter: OK')" && \
    python3 -c "import tree_sitter_php; print('tree-sitter-php: OK')"

CMD ["/bin/bash"]
