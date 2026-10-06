# MatrixOne TPCC Nightly Profile Harness

The profile file is JSON-formatted YAML so it can be edited by hand and parsed with the Python standard library.

Use `python3 tools/render_tpcc_repair.py --dry-run` to inspect the current profile decision. After making the scoped repair, run `python3 tools/render_tpcc_repair.py --apply` to write the artifact and update Postgres.
