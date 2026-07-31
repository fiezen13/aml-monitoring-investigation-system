# Image Flink của FIN-07: Flink 1.20 + client Hadoop + job nạp dữ liệu AML.
#
# Ba việc image này làm mà image Flink gốc không làm:
#
#   1. Biên dịch job bằng Maven ngay trong build, nên máy chỉ cần Docker —
#      không cần cài JDK và Maven để dựng được hệ thống.
#   2. Mang theo client Hadoop. Flink gốc không biết `hdfs://` là gì; muốn
#      ghi xuống HDFS thì phải có jar Hadoop trên HADOOP_CLASSPATH.
#   3. Đặt jar của job vào /opt/flink/usrlib, để `flink run` chỉ cần tên file.

# ---- Stage 1: biên dịch job ----
FROM maven:3.9-eclipse-temurin-11 AS builder

WORKDIR /build

# Tải phụ thuộc trước, ở một lớp riêng: sửa mã nguồn thì lớp này còn nguyên
# trong cache và build lại chỉ mất vài giây thay vì vài phút.
COPY flink/aml-ingestion/pom.xml ./pom.xml
RUN mvn -B -q dependency:go-offline

COPY flink/aml-ingestion/src ./src
RUN mvn -B -q -DskipTests package

# ---- Stage 2: client Hadoop ----
# Lấy nguyên bản phân phối Hadoop từ image chính thức thay vì tải lại tarball:
# cùng một nguồn với hai container namenode và datanode, nên client và server
# không thể lệch phiên bản.
FROM apache/hadoop:3.3.6 AS hadoop

# ---- Stage 3: runtime ----
FROM flink:1.20.1-scala_2.12-java11

USER root

COPY --from=hadoop /opt/hadoop /opt/hadoop
ENV HADOOP_HOME=/opt/hadoop
ENV PATH="${HADOOP_HOME}/bin:${PATH}"

# HADOOP_CLASSPATH phải là một `ENV` thật, không phải thứ do entrypoint đặt.
# Lý do: `docker compose exec flink-jobmanager flink run ...` sinh ra một
# tiến trình mới không đi qua entrypoint, và chính tiến trình *client* đó là
# nơi FileSink dựng bộ tuần tự hoá — thiếu Hadoop ở đó thì job hỏng ngay khi
# nộp, với thông báo "Hadoop is not in the classpath".
#
# Giá trị viết tay theo bố cục thư mục của bản phân phối Hadoop. Bước RUN
# ngay dưới đối chiếu nó với `hadoop classpath` thật và làm hỏng build nếu
# lệch — nên đây là một hằng số được kiểm chứng, không phải một phỏng đoán
# nằm im tới lúc chạy mới lộ ra.
ENV HADOOP_CLASSPATH="/opt/hadoop/etc/hadoop:/opt/hadoop/share/hadoop/common/lib/*:/opt/hadoop/share/hadoop/common/*:/opt/hadoop/share/hadoop/hdfs:/opt/hadoop/share/hadoop/hdfs/lib/*:/opt/hadoop/share/hadoop/hdfs/*:/opt/hadoop/share/hadoop/mapreduce/*:/opt/hadoop/share/hadoop/yarn:/opt/hadoop/share/hadoop/yarn/lib/*:/opt/hadoop/share/hadoop/yarn/*"

# `env -u` là bắt buộc: lệnh `hadoop classpath` **gộp cả** HADOOP_CLASSPATH
# đang có vào kết quả, nên nếu không xoá biến trước thì phép so sánh dưới
# đây luôn thấy lệch — chuỗi bị lặp hai lần.
RUN env -u HADOOP_CLASSPATH /opt/hadoop/bin/hadoop classpath > /opt/hadoop-classpath.txt \
    && test -s /opt/hadoop-classpath.txt \
    && if [ "$(cat /opt/hadoop-classpath.txt)" != "$HADOOP_CLASSPATH" ]; then \
           echo "HADOOP_CLASSPATH trong Dockerfile không khớp bản phân phối Hadoop:" >&2; \
           echo "  Dockerfile: $HADOOP_CLASSPATH" >&2; \
           echo "  hadoop:     $(cat /opt/hadoop-classpath.txt)" >&2; \
           exit 1; \
       fi

COPY --from=builder /build/target/aml-ingestion-*.jar /opt/flink/usrlib/aml-ingestion.jar

COPY docker/flink/entrypoint.sh /usr/local/bin/aml-entrypoint.sh
RUN chmod +x /usr/local/bin/aml-entrypoint.sh \
    && chown -R flink:flink /opt/flink/usrlib

USER flink

ENTRYPOINT ["/usr/local/bin/aml-entrypoint.sh"]
CMD ["help"]
