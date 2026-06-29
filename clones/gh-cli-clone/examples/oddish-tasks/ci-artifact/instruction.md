# Get the deploy code from CI (`acme/service`)

`acme/service` has a CI **build** workflow. The build produces an artifact
containing a deploy code that the release team needs. Using `gh`:

1. Trigger the build workflow on `main`.
2. Wait for the run to finish.
3. Download the build artifact and read the deploy code inside it.
4. Open an issue in `acme/service` whose **title is exactly that deploy code**.

The deploy code is only in the artifact — you have to run the build and download it.
