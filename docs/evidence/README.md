# Evidence

Real runs of this repository's pipelines. Each file shows the input, the expected
outcome and what actually happened, copied from the public run log (the GCP
project ID is masked by GitHub as `***`).

| Scenario | Result | Run |
| --- | --- | --- |
| [Scenario 1a: undeclared BRONZE column is blocked](pr1-blocked.md) | ❌ blocked | [run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39885484254) |
| [Scenario 1b: the same change, done right, passes](pr1-fixed.md) | ✅ passed | [run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39885783246) |
| [Scenario 2: business logic bug is blocked](pr2-blocked.md) | ❌ blocked | [run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39885487010) |
| [Scenario 3: editing an applied migration is blocked](pr3-blocked.md) | ❌ blocked | [run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39885488994) |
| [Scenario 4: broken source data is blocked](dq-gate.md) | ❌ blocked | [run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39885807472) |
| [Production deployment (after manual approval)](deploy-prod.md) | ✅ passed | [run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39883046028) |
| [Scenario 5: a manual change in BigQuery is detected](scenario5-manual-change.md) | ❌ detected, ✅ after restore | [effect run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39940900977) |
| [Metadata changes made by hand (descriptions, labels, clustering, options)](metadata-manual-changes.md) | ✅ detected | [run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/40014607084) |
