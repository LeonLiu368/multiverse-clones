# CI reference

These are the GitHub Actions workflows that built and published the clone images when this repo
lived in the `abundant-ai` org. They're kept here as a record of how each image was built and
tagged, not as working CI.

They publish to `ghcr.io/abundant-ai`, which this repository can't write to, so they would fail
if run from here. To use one again, move it back into `.github/workflows/` and change the
registry namespace (`NS` and the `ghcr.io/abundant-ai/...` image names) to one you can push to.

- `publish-images.yml`: builds each clone's service and agent images and pushes them, one job per clone.
- `publish-jira-slack.yml`: builds the Jira and Slack gateway images on top of their in-org base images.
