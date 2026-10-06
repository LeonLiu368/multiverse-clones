# Descriptor Backref Repair Artifact

`/app/artifacts/descriptor_backref_repair.json` is the handoff artifact for CRDB-63963.

Required top-level keys:

- `ticket`: string ticket identifier.
- `sentry_event`: string Sentry event identifier.
- `artifact_version`: integer schema version.
- `affected_descriptor_ids`: array of integer relation descriptor IDs selected for repair.
- `repairs`: array of repair objects.
- `untouched_descriptor_ids`: array of integer relation descriptor IDs intentionally left alone.
- `broad_workaround_rejected`: string explanation of the avoided broad workaround.

Each `repairs` entry must contain:

- `relation_id`: integer relation descriptor ID.
- `relation_name`: string relation name.
- `referenced_descriptor_id`: integer missing referenced descriptor ID.
- `action`: string action name.
- `reason`: string scoped rationale.
