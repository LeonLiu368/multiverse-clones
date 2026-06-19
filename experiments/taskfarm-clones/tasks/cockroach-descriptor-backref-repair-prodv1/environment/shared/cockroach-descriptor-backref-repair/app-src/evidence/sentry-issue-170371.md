# Sentry Issue 170371

Panic message:

```text
validate.go:358: relation x (193): invalid depended-on-by relation back reference: referenced descriptor ID 400: referenced descriptor not found
keys: [sql.schema.validation_errors.read.backward_references.relation]
```

Stack focus:

- `pkg/sql/catalog/tabledesc/validate.go:358`
- `pkg/sql/repair.go:82`
- `pkg/sql/repair.go:694`
- `pkg/sql/catalog/descs/descriptor.go:668`

Runtime tags:

- Cockroach release: v25.4.0
- SHA: 4f4179243a351bc48c00dd9243dc56b8af98e210
- Platform: linux amd64
- Goroutines: 1882
