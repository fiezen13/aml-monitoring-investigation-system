#!/usr/bin/env bash
# Kiểm tra Hadoop có trên classpath rồi bàn giao cho entrypoint gốc của Flink.
#
# `HADOOP_CLASSPATH` được đặt bằng `ENV` trong Dockerfile, không đặt ở đây —
# `docker exec` không đi qua entrypoint, mà `flink run` lại chạy đúng theo
# đường đó. File này chỉ còn giữ vai trò lưới an toàn: nếu biến vắng mặt thì
# nói ra ngay lúc khởi động, thay vì để job hỏng lúc nộp với một thông báo
# khó lần ra nguyên nhân.

set -euo pipefail

if [ -z "${HADOOP_CLASSPATH:-}" ] && [ -r /opt/hadoop-classpath.txt ]; then
    HADOOP_CLASSPATH="$(cat /opt/hadoop-classpath.txt)"
    export HADOOP_CLASSPATH
    echo "aml-entrypoint: HADOOP_CLASSPATH chưa được đặt, đã lấy từ /opt/hadoop-classpath.txt" >&2
fi

if [ -z "${HADOOP_CLASSPATH:-}" ]; then
    echo "aml-entrypoint: thiếu HADOOP_CLASSPATH — Flink sẽ không ghi được hdfs://" >&2
    exit 1
fi

exec /docker-entrypoint.sh "$@"
