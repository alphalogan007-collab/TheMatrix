FROM debian:bookworm-slim

# Core utilities + redis-cli
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl wget ca-certificates \
    redis-tools \
    jq vim less git \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI (static binary — no daemon needed, uses mounted socket)
RUN DOCKER_VER=27.3.1 \
    && wget -qO- "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VER}.tgz" \
    | tar -xz -C /usr/local/bin --strip-components=1 docker/docker

# docker compose v2 plugin
RUN mkdir -p /usr/local/lib/docker/cli-plugins \
    && wget -qO /usr/local/lib/docker/cli-plugins/docker-compose \
       "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \
    && chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# ttyd — web terminal server
RUN wget -q -O /usr/local/bin/ttyd \
    "https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64" \
    && chmod +x /usr/local/bin/ttyd

COPY .bashrc /root/.bashrc

WORKDIR /workspace

EXPOSE 7681

CMD ["ttyd", \
     "--port", "7681", \
     "--writable", \
     "-t", "fontSize=14", \
     "-t", "theme={\"background\":\"#0d1117\",\"foreground\":\"#c9d1d9\",\"cursor\":\"#58a6ff\"}", \
     "bash", "--login"]
