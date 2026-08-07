# Graph suitability report

Status for v0.1.0 design: **PASS**, subject to the generated release quality report.

Graph construction uses Bank View only. Supported nodes include customers, businesses, accounts, devices, merchants, tokenized counterparties, sessions, and coarse IP tokens. Supported edges include customer ownership, beneficial ownership, device use/sharing, merchant operation, transaction flows, and temporal session activity.

Transaction rows expose mutually exclusive internal-account or tokenized-external endpoints, so flow edges never require hidden actor IDs. Relationship rows record direction, method, confidence, observation count, validity, and known-from time. This supports temporal and heterogeneous graphs while distinguishing observed facts from probabilistic relationships.

The automated report measures account/counterparty node count, event and unique edges, connected components, largest component, event-degree statistics, observable relationship edges, and synthetic scenario-network counts. Referential and split checks ensure internal endpoints resolve and scenario networks do not cross evaluation cohorts. Realized values are stored in `reports/graph_suitability_report.json`.

Ground-truth networks are evaluation targets, not graph inputs. In particular, `true_controller_id`, true coordination, scenario IDs, and hidden intent are excluded from feature-visible Parquet files.
