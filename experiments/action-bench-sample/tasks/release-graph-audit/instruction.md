REL-884 needs a release-captain handoff before today's train review.

Release engineering keeps the current train state in `releasectl` so the on-call can work from the same item graph used in the release room. Use that operations interface to discover the submission schema, identify the owner escalations that need to happen before the train can move, then submit the handoff through the release tooling.

The handoff should make clear who needs to act, why each escalation matters, and what order dependency-linked work should be resolved in. Include enough evidence that the release captain can forward each escalation without redoing your investigation.
