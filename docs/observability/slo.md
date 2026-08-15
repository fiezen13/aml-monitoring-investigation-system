# FIN-07 SLI and SLO framework

No business-approved SLO was found in the repository. Values below are either measured SLIs or explicitly provisional engineering targets; they must not be presented as approved commitments.

| Capability | Measured SLI | Provisional engineering target | Approved SLO |
|---|---|---|---|
| API availability | non-5xx requests / all requests | ≥99% over 30 days | Not defined |
| API latency | share below route latency threshold; p95/p99 | p95 <2s for 10m alert only | Not defined |
| Investigation completion | completed or safe human-review outcomes / started | Establish baseline first | Not defined |
| Investigation latency | `fin07_investigation_duration_seconds` distribution | Alert after baseline | Not defined |
| Worker processing | completed / started jobs; queue wait and duration | queue depth <100 is provisional | Not defined |
| Gemini success | successful Gemini calls / all calls | Establish model/agent baseline | Not defined |
| Tool success | successful allow-listed calls / all calls by tool | Establish per-tool baseline | Not defined |
| Agent completion | successful logical runs / all logical runs by agent | Establish baseline | Not defined |
| Schema-valid output | valid structured responses / all provider responses | Target should be reviewed after baseline | Not defined |
| Critic PASS | PASS validations / all validations | Quality proxy only; no target | Not defined |
| Unsupported claim rate | unsupported issues / validations | Lower is better; baseline required | Not defined |

Critic PASS measures consistency with available evidence and deterministic validation. It is not a truth metric. Human review is a safety outcome, not automatically an operational failure.

Error budgets must not be calculated until owners approve an SLO window, target, eligible traffic, exclusions, and incident policy.
