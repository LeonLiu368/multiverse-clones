# Trigger CI and report with `gh`

`gh` is installed and authenticated. The repo **`acme/pipeline`** contains a
workflow file (a `workflow_dispatch` workflow). Using `gh`:

1. List the workflows in `acme/pipeline` (`gh workflow list`).
2. Dispatch that workflow on the `main` branch (`gh workflow run <file> --ref main`).
3. List the runs (`gh run list`).
4. As confirmation, open an issue in `acme/pipeline` whose **title is exactly
   the workflow file name** you found in step 1 (it is `build.yml`).
