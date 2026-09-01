#!/usr/bin/env bash
# Local smoke test. Uses mock Gemini and does not require Google credentials.
set -euo pipefail

compose=(docker compose --profile observability)
export OTEL_ENABLED=true
export LLM_MODE=mock

"${compose[@]}" up -d --build --wait

api_url="http://127.0.0.1:${API_PORT:-8000}"
prom_url="http://127.0.0.1:${PROMETHEUS_PORT:-9090}"
jaeger_url="http://127.0.0.1:${JAEGER_UI_PORT:-16686}"
web_url="http://127.0.0.1:${WEB_PORT:-5173}"

curl -fsS "${api_url}/health/ready" >/dev/null
api_metrics="$(curl -fsS "${api_url}/metrics")"
grep -q "fin07_http_requests" <<<"${api_metrics}"

alert_id="$(curl -fsS "${api_url}/api/v1/alerts" | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["alert_id"])')"
start_response="$(curl -fsS -X POST "${api_url}/api/v1/alerts/${alert_id}/investigate")"
investigation_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["investigation_id"])' <<<"${start_response}")"

investigation_status="QUEUED"
for _ in $(seq 1 30); do
  investigation_response="$(curl -fsS "${api_url}/api/v1/investigations/${investigation_id}")"
  investigation_status="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"${investigation_response}")"
  case "${investigation_status}" in
    COMPLETED|INSUFFICIENT_EVIDENCE|NEEDS_HUMAN_REVIEW) break ;;
    FAILED) echo "Investigation ${investigation_id} failed" >&2; exit 1 ;;
  esac
  sleep 2
done
case "${investigation_status}" in
  COMPLETED|INSUFFICIENT_EVIDENCE|NEEDS_HUMAN_REVIEW) ;;
  *) echo "Investigation ${investigation_id} did not finish: ${investigation_status}" >&2; exit 1 ;;
esac

for _ in $(seq 1 30); do
  agent_query="$(curl -fsS "${prom_url}/api/v1/query?query=fin07_agent_runs_total")"
  if grep -q '"result":\[{' <<<"${agent_query}"; then
    break
  fi
  sleep 2
done

curl -fsS "${prom_url}/-/healthy" >/dev/null
prom_targets="$(curl -fsS "${prom_url}/api/v1/targets")"
grep -q 'otel-collector' <<<"${prom_targets}"
jaeger_services="$(curl -fsS "${jaeger_url}/api/services")"
grep -q 'fin07-worker' <<<"${jaeger_services}"
"${compose[@]}" exec -T prometheus wget -q -O /dev/null http://otel-collector:13133/
loki_labels="$("${compose[@]}" exec -T prometheus wget -q -O - http://loki:3100/loki/api/v1/labels)"
grep -q 'status' <<<"${loki_labels}"

# The cockpit is same-origin but remains protected by the FIN-07 session. The
# smoke test never prints or persists the bearer token.
unauth_code="$(curl -sS -o /dev/null -w '%{http_code}' "${web_url}/grafana/api/health")"
test "${unauth_code}" = "401"
login_response="$(curl -fsS -H 'Content-Type: application/json' \
  -d '{"email":"hung.nq@velrix.vn","password":"demo-password"}' \
  "${web_url}/api/v1/auth/login")"
session_token="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])' <<<"${login_response}")"
dashboard_response="$(curl -fsS --cookie "fin07_session=${session_token}" \
  "${web_url}/grafana/api/dashboards/uid/fin07-observability")"
grep -q 'FIN-07 — Tổng quan vận hành' <<<"${dashboard_response}"
viewer_orgs="$(curl -fsS --cookie "fin07_session=${session_token}" "${web_url}/grafana/api/user/orgs")"
grep -q 'Viewer' <<<"${viewer_orgs}"

echo "FIN-07 observability smoke test passed"
