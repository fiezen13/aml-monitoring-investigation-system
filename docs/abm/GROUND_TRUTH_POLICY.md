# Ground-truth policy

Ground truth describes simulator causality, not legal adjudication. AML rows represent synthetic typology involvement for detection research; the release explicitly sets `prevalence_claim=false`.

Ground truth remains normalized:

- `entity_labels`: customer/account role and active interval;
- `transaction_labels`: scenario stage for each causal transaction;
- `scenario_instances`: typology, network, benchmark status, interval, and counts;
- `networks` and `network_members`: isolated scenario topology;
- `hard_negative_instances`: legitimate confusing episodes;
- `split_assignments`: canonical evaluation cohorts.

The hidden view additionally records causal actors, true coordination, controller, and intent. None of these columns may appear in Bank View. Binary labels must be derived downstream for a declared prediction target and point in time; the canonical release does not flatten roles, stages, entities, and networks into one label.

Transaction-, account-, customer-, network-, and snapshot-level labels can be derived by joining ground truth after feature computation. Point-in-time evaluation must include only labels whose active interval and prediction horizon match the task. Hidden-test ground truth should be withheld from model developers in a benchmark deployment.
