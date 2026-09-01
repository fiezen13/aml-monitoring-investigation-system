// =====================================================================
// FIN-07 — pipeline CI/CD hoàn chỉnh
//
// Vì sao Jenkins chứ không phải một dịch vụ CI đám mây: đây là hệ thống
// giám sát AML, tài liệu đóng dấu "Nội bộ — Hạn chế". Tổ chức tài chính
// nhận bàn giao sẽ chạy pipeline trong mạng của họ, không đẩy mã nguồn và
// bí mật lên runner của bên thứ ba. Jenkins tự host là thứ họ dùng được.
//
// Phân vai với GitHub Actions (.github/workflows/ci.yml):
//
//   GitHub Actions  — cổng chặn merge. Nhanh, chạy trên mọi pull request,
//                     là status check mà branch protection kiểm.
//   Jenkins (đây)   — pipeline giao hàng. Build, kiểm thử, triển khai
//                     staging, phê duyệt, triển khai production-like,
//                     kiểm tra khói, quay lui.
//
// Cả hai gọi CÙNG các script trong ci/. Không có logic nào viết hai lần,
// nên hai hệ thống không lệch nhau được — đó là điều kiện để việc chạy
// song song hai hệ thống không trở thành nợ kỹ thuật.
//
// Tài liệu: docs/operations/README.md#cicd-cổng-chặn-merge-và-pipeline-giao-hàng
// =====================================================================

pipeline {

    // Agent cần: docker, docker compose v2, python3.11, node 22, psql, jq,
    // curl, git. Xem docs/operations/README.md#cicd-cổng-chặn-merge-và-pipeline-giao-hàng mục 3 để dựng agent.
    agent { label 'fin07' }

    options {
        timestamps()
        ansiColor('xterm')
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '10'))
        // Hai lượt triển khai cùng một môi trường chồng lên nhau là cách
        // nhanh nhất để có một môi trường không ai biết đang chạy gì.
        disableConcurrentBuilds()
        skipDefaultCheckout(false)
    }

    environment {
        // Đổi được từ cấu hình controller (jenkins/casc.yaml → globalNodeProperties)
        // thay vì phải sửa file này. Cần thiết khi chạy pipeline với registry
        // nội bộ, và khi tổ chức khác nhận bàn giao rồi đẩy image vào registry
        // của họ — lúc đó Jenkinsfile không phải là thứ họ phải sửa.
        REGISTRY   = "${env.FIN07_REGISTRY ?: 'ghcr.io'}"
        IMAGE_REPO = "${env.FIN07_IMAGE_REPO ?: 'ai20k-build-phase-cohort-3/p-022'}"
        PYTHON     = 'python3'

        // Tag di động (tên nhánh, bỏ dấu gạch chéo) KHÔNG tính ở đây.
        //
        // Bản trước viết:
        //     MOVING_TAG = "${env.BRANCH_NAME?.replaceAll('/', '-') ?: 'manual'}"
        //
        // BRANCH_NAME chỉ tồn tại ở job multibranch. Với job Pipeline thường
        // nó là null, biểu thức trả về null, và Jenkins từ chối NGUYÊN khối
        // environment với thông báo:
        //
        //     One or more variables have some issues with their values: MOVING_TAG
        //
        // Hậu quả không hề tương xứng với nguyên nhân: toàn bộ stages bị bỏ
        // qua, post chạy ngoài ngữ cảnh node rồi hỏng tiếp, và ở đầu log
        // không có dòng lỗi nào — build chỉ đơn giản là checkout xong rồi kết
        // thúc. Phải đọc tới giữa stack trace mới thấy tên biến.
        //
        // Nay tính bằng shell ở đúng chỗ cần dùng: không có biểu thức Groovy
        // nào chạy trước stages, nên không có gì hỏng trước stages được.
    }

    parameters {
        booleanParam(
            name: 'SKIP_DEPLOY',
            defaultValue: false,
            description: 'Chỉ build và kiểm thử, không triển khai. Dùng khi cần kiểm tra nhanh một nhánh.'
        )
    }

    stages {

        // -------------------------------------------------------------
        stage('Kiểm tra môi trường') {
            steps {
                sh '''
                    set -eu
                    missing=""
                    for tool in docker python3 node npm psql jq curl git; do
                        command -v "$tool" >/dev/null 2>&1 || missing="${missing} ${tool}"
                    done
                    if [ -n "$missing" ]; then
                        echo "Agent thiếu công cụ:${missing}"
                        echo "Xem docs/operations/README.md#cicd-cổng-chặn-merge-và-pipeline-giao-hàng mục 3 để dựng agent đúng."
                        exit 1
                    fi
                    docker compose version >/dev/null 2>&1 || {
                        echo "Cần Docker Compose v2 (lệnh 'docker compose', không phải 'docker-compose')"
                        exit 1
                    }
                    chmod +x ci/*.sh db/init/*.sh
                    echo "Commit:  $(git rev-parse --short HEAD)"
                    echo "Nhánh:   ${BRANCH_NAME:-không rõ}"
                '''
            }
        }

        // -------------------------------------------------------------
        // Ba việc không phụ thuộc nhau thì chạy cùng lúc. Lint hỏng vẫn
        // muốn biết luôn test có hỏng không, để sửa một lượt.
        stage('Kiểm tra chất lượng') {
            parallel {

                stage('Lint') {
                    steps {
                        sh '''
                            set -eu
                            python3 -m venv .venv-lint
                            . .venv-lint/bin/activate
                            pip install --quiet --disable-pip-version-check -r requirements-dev.txt
                            PYTHON="$(pwd)/.venv-lint/bin/python" ./ci/lint.sh
                        '''
                    }
                }

                stage('Kiểm thử') {
                    steps {
                        sh '''
                            set -eu
                            python3 -m venv .venv-test
                            . .venv-test/bin/activate
                            pip install --quiet --disable-pip-version-check -r requirements-dev.txt
                            PYTHON="$(pwd)/.venv-test/bin/python" ./ci/test.sh
                        '''
                    }
                    post {
                        always {
                            junit allowEmptyResults: true, testResults: 'pytest-report.xml'
                            archiveArtifacts artifacts: 'coverage.xml', allowEmptyArchive: true
                        }
                    }
                }

                stage('Giao diện') {
                    steps {
                        dir('web') {
                            sh '''
                                set -eu
                                npm ci --no-audit --no-fund
                                npm run typecheck
                                npm run build
                            '''
                        }
                    }
                }
            }
        }

        // -------------------------------------------------------------
        stage('Build image') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'fin07-registry',
                    usernameVariable: 'REGISTRY_USER',
                    passwordVariable: 'REGISTRY_TOKEN'
                )]) {
                    sh '''
                        set -eu
                        echo "$REGISTRY_TOKEN" | docker login "$REGISTRY" -u "$REGISTRY_USER" --password-stdin
                        # BRANCH_NAME rỗng ở job Pipeline thường (chỉ multibranch
                        # mới đặt biến này), nên có giá trị thay thế.
                        MOVING_TAG="$(echo "${BRANCH_NAME:-manual}" | tr '/' '-')"
                        export MOVING_TAG
                        echo "Tag di động: ${MOVING_TAG}"
                        PUSH=true ./ci/build-images.sh
                        docker logout "$REGISTRY"
                    '''
                }
                script {
                    // Ghi tag vào mô tả build: mở Jenkins ra là biết ngay lượt
                    // này sinh image nào, không phải lần mò trong log.
                    def tags = readFile('.image-tags').trim()
                    currentBuild.description = tags.readLines().find { it.startsWith('IMAGE_TAG=') }
                }
                archiveArtifacts artifacts: '.image-tags', allowEmptyArchive: false
            }
        }

        // -------------------------------------------------------------
        // develop → staging, tự động, không hỏi ai.
        stage('Triển khai staging') {
            when {
                allOf {
                    branch 'develop'
                    expression { !params.SKIP_DEPLOY }
                }
            }
            steps {
                withCredentials([
                    usernamePassword(credentialsId: 'fin07-registry',
                                     usernameVariable: 'REGISTRY_USER',
                                     passwordVariable: 'REGISTRY_TOKEN'),
                    string(credentialsId: 'fin07-staging-postgres-password',
                           variable: 'POSTGRES_PASSWORD'),
                    string(credentialsId: 'fin07-staging-agent-db-password',
                           variable: 'FIN07_AGENT_DB_PASSWORD'),
                    string(credentialsId: 'fin07-staging-google-api-key',
                           variable: 'GOOGLE_API_KEY')
                ]) {
                    sh '''
                        set -eu
                        echo "$REGISTRY_TOKEN" | docker login "$REGISTRY" -u "$REGISTRY_USER" --password-stdin
                        # Không đặt giá trị mặc định: một docker context phải được
                        # tạo bằng tay trên agent, và mặc định trỏ vào cái chưa tồn
                        # tại thì mọi lệnh docker hỏng với 'context not found' —
                        # thông báo không hề gợi ý rằng chỉ cần bỏ trống biến này.
                        # Bỏ trống nghĩa là triển khai lên chính máy đang chạy agent,
                        # đúng cho trường hợp Jenkins và môi trường ở chung một máy.
                        export API_URL="${STAGING_API_URL:-http://localhost:8000}"
                        export WEB_URL="${STAGING_WEB_URL:-http://localhost:5173}"
                        ./ci/deploy.sh staging
                        docker logout "$REGISTRY"
                    '''
                }
            }
        }

        // -------------------------------------------------------------
        // main → production-like, nhưng phải có người bấm.
        //
        // Cổng này không phải thủ tục hành chính. Nguyên tắc NT3 của dự án là
        // con người quyết định cuối cùng ở mọi đường dẫn có hậu quả; đưa một
        // phiên bản mới vào môi trường mà hội đồng nghiệm thu nhìn vào là một
        // đường dẫn như vậy.
        stage('Chờ phê duyệt') {
            when {
                allOf {
                    branch 'main'
                    expression { !params.SKIP_DEPLOY }
                }
            }
            options {
                timeout(time: 12, unit: 'HOURS')
            }
            steps {
                script {
                    def tag = readFile('.image-tags').trim()
                    def decision = input(
                        message: "Triển khai lên production-like?\n\n${tag}",
                        ok: 'Triển khai',
                        submitter: 'bao,mlro',
                        submitterParameter: 'nguoiPheDuyet',
                        parameters: [
                            text(name: 'lyDo',
                                 defaultValue: '',
                                 description: 'Lý do triển khai — ghi vào nhật ký build, bắt buộc')
                        ]
                    )
                    if (!decision.lyDo?.trim()) {
                        error('Phê duyệt phải kèm lý do. Huỷ lượt triển khai này.')
                    }
                    env.APPROVER = decision.nguoiPheDuyet
                    env.APPROVAL_REASON = decision.lyDo
                    echo "Người phê duyệt: ${env.APPROVER}"
                    echo "Lý do: ${env.APPROVAL_REASON}"
                    currentBuild.description = "${currentBuild.description} · duyệt bởi ${env.APPROVER}"
                }
            }
        }

        stage('Triển khai production-like') {
            when {
                allOf {
                    branch 'main'
                    expression { !params.SKIP_DEPLOY }
                }
            }
            steps {
                withCredentials([
                    usernamePassword(credentialsId: 'fin07-registry',
                                     usernameVariable: 'REGISTRY_USER',
                                     passwordVariable: 'REGISTRY_TOKEN'),
                    string(credentialsId: 'fin07-prodlike-postgres-password',
                           variable: 'POSTGRES_PASSWORD'),
                    string(credentialsId: 'fin07-prodlike-agent-db-password',
                           variable: 'FIN07_AGENT_DB_PASSWORD'),
                    string(credentialsId: 'fin07-prodlike-google-api-key',
                           variable: 'GOOGLE_API_KEY')
                ]) {
                    sh '''
                        set -eu
                        echo "$REGISTRY_TOKEN" | docker login "$REGISTRY" -u "$REGISTRY_USER" --password-stdin
                        # Xem ghi chú ở stage triển khai staging.
                        export API_URL="${PRODLIKE_API_URL:-http://localhost:8000}"
                        export WEB_URL="${PRODLIKE_WEB_URL:-http://localhost:5173}"
                        ./ci/deploy.sh prodlike
                        docker logout "$REGISTRY"
                    '''
                }
            }
        }
    }

    post {
        always {
            sh '''
                rm -rf .venv-lint .venv-test || true
                docker logout "$REGISTRY" 2>/dev/null || true
            '''
            cleanWs(deleteDirs: true, notFailBuild: true)
        }
        success {
            echo "Build ${env.BUILD_NUMBER} đạt."
        }
        unstable {
            echo "Build ${env.BUILD_NUMBER} không ổn định — có kiểm thử trượt."
        }
        failure {
            echo "Build ${env.BUILD_NUMBER} thất bại ở giai đoạn ${env.STAGE_NAME}."
            // Kênh thông báo cấu hình ở docs/operations/README.md#cicd-cổng-chặn-merge-và-pipeline-giao-hàng mục 7. Cố ý để trống
            // thay vì cắm sẵn webhook giả — một thông báo không tới nơi còn
            // tệ hơn không có thông báo, vì người ta tưởng là có.
        }
        aborted {
            echo "Build ${env.BUILD_NUMBER} bị huỷ — có thể do hết hạn chờ phê duyệt."
        }
    }
}
