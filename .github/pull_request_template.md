## Summary

<!-- What changes and why. -->

## Type of change

- [ ] bqchange migration (versioned `V*`, repeatable `R__`, always `A__`)
- [ ] dbt model / source / test
- [ ] CI/CD or tooling

## Checklist

- [ ] New BRONZE columns are declared in `dbt/models/silver/ecommerce/_ecommerce__sources.yml`
- [ ] Versioned scripts are new files (applied scripts are never edited)
- [ ] Data quality tests cover new columns and models
- [ ] GOLD contract updated when output columns change
- [ ] CI integration job is green on the pull request clone
