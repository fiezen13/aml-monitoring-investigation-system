# Jenkins controller của FIN-07, dựng từ mã nguồn.
#
# Dựng lại được từ đầu là yêu cầu, không phải tiện nghi: FIN-07-ARC-001 mục 7
# ghi "không có môi trường nào được dựng bằng thao tác tay". Controller cũng
# là một môi trường.

FROM jenkins/jenkins:2.568.1-lts-jdk21

USER root

# Docker CLI để pipeline build được image. Không cài Docker daemon — controller
# dùng socket của máy chủ (xem jenkins/docker-compose.yml).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
         | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
         https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
         > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

USER jenkins

COPY --chown=jenkins:jenkins plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt --latest true

# Cấu hình đặt NGOÀI /var/jenkins_home. Thư mục đó là volume, nên file copy
# vào lúc build sẽ bị nội dung volume cũ che mất: sửa casc.yaml, build lại,
# khởi động lại — và Jenkins vẫn chạy cấu hình của lần đầu tiên, không báo gì.
COPY --chown=jenkins:jenkins casc.yaml /usr/share/jenkins/casc/jenkins.yaml

ENV CASC_JENKINS_CONFIG=/usr/share/jenkins/casc/jenkins.yaml
# Bỏ trình hướng dẫn cài đặt: mọi cấu hình đã nằm trong casc.yaml, bấm qua
# giao diện lần nữa chỉ tạo ra khác biệt không ai ghi lại.
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false -Dhudson.model.DownloadService.noSignatureCheck=true"
