# Agent build của FIN-07.
#
# Danh sách công cụ dưới đây khớp đúng bước "Kiểm tra môi trường" ở đầu
# Jenkinsfile. Hai chỗ lệch nhau thì pipeline sẽ đỏ ở dòng đầu tiên kèm
# thông báo rõ ràng, chứ không đỏ giữa chừng vì một lệnh không tồn tại.

FROM jenkins/inbound-agent:3384.v60d89463d9e0-1-jdk17

USER root

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg jq make \
        python3 python3-venv python3-pip \
        postgresql-client \
    && install -m 0755 -d /etc/apt/keyrings \
    # --- Docker CLI và Compose v2 ---
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
         | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
         https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
         > /etc/apt/sources.list.d/docker.list \
    # --- Node 22 ---
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
         | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] \
         https://deb.nodesource.com/node_22.x nodistro main" \
         > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        docker-ce-cli docker-compose-plugin nodejs shellcheck \
    && rm -rf /var/lib/apt/lists/*

# Cho user jenkins dùng được socket Docker của máy chủ. GID 999 là mặc định
# của nhóm docker trên Debian và Ubuntu; máy chủ dùng GID khác thì sửa ở đây.
ARG DOCKER_GID=999
RUN groupadd -g "${DOCKER_GID}" docker-host 2>/dev/null || true \
    && usermod -aG "${DOCKER_GID}" jenkins

USER jenkins
