# Data removed

This seed was a real company's Slack export from 2021. People were anonymized, but the messages are that company's internal conversations, so it was removed from the public copy of this repository, including its history.

Gateway builds default to the `slack-seed:eng-2021q1` image, whose source is no longer here. To use another
seed, put a Slack export under `seeds/<name>/export/`, build a seed image from it with
`.github/workflows/build-seed-image.yml`, then run `DATASET=<name> ./build-gateway.sh` (or set `SEED=<image>`).
`seeds/tiny/` is a small test workspace to start from.
