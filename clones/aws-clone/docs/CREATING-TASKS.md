# Creating Tasks With aws-clone

Use `aws-clone` when AWS evidence should be essential to the task, but the task must remain local, deterministic, and safe to run without real cloud credentials.

## Compose Pattern

Mount task state only into the AWS sidecar:

```yaml
aws:
  image: ghcr.io/abundant-ai/aws-clone-service:<tag>@sha256:<digest>
  hostname: aws
  environment:
    AWS_CLONE_STATE_FILE: /data/aws-clone/state.json
    AWS_CLONE_RUNTIME_STATE_FILE: /var/lib/aws-clone/state.json
    AWS_CLONE_ENABLE_ADMIN_API: "1"
    AWS_CLONE_ADMIN_TOKEN: ${AWS_CLONE_ADMIN_TOKEN}
  volumes:
    - ./data/aws-clone/state.json:/data/aws-clone/state.json:ro
    - aws-clone-runtime:/var/lib/aws-clone
```

Copy only agent tools into the agent image:

```dockerfile
FROM ghcr.io/abundant-ai/aws-clone-service:<tag>@sha256:<digest> AS aws-tools
COPY --from=aws-tools /usr/local/bin/aws /usr/local/bin/awslocal /usr/local/bin/
COPY --from=aws-tools /opt/awscli /opt/awscli
ENV PYTHONPATH=/opt/awscli
```

Do not mount `data/aws-clone/state.json` into the agent. Do not copy `aws-clonectl`. Do not pass `AWS_CLONE_ADMIN_TOKEN`.

## Evidence Design

Good tasks make AWS evidence necessary without leaking answers:

- Put the symptom in Linear/Jira, Slack, Gauge, or Sentry context.
- Seed AWS state that confirms or falsifies the suspected cause.
- Include plausible distractors, stale resources, or superseded logs.
- Require the agent to cite evidence discovered through `aws` or `awslocal`.
- Let verifiers inspect outcomes through service APIs or admin endpoints, not raw state files.

Recommended workflow:

```text
Linear/Jira issue -> Slack context -> Gauge alert -> Sentry issue -> AWS state/logs/queue/object/config -> code fix -> tests/replay -> GitHub PR -> optional AWS mutation -> Slack/Linear handoff
```

## Example Task Shapes

- SQS DLQ investigation: a retry queue has poison messages, a DLQ redrive policy, and CloudWatch logs showing the failure mode.
- S3 missing manifest: a batch job fails because a manifest key or prefix differs from code assumptions.
- DynamoDB idempotency bug: an item is stuck in the wrong state, or conditional writes are using the wrong key.
- SSM bad config: a retry limit, feature flag, or endpoint parameter is wrong.
- EventBridge missing target: a scheduled job has a rule but no live target, or a target points at a stale function.
- CloudWatch log stacktrace: seeded log events provide the stack trace needed to find the failing code path.

Prompts should not mention LocalStack, seed files, admin APIs, verifier tokens, or hidden expected mutations.

## Pilot Integration Checklist

Integrate `aws-clone` into one pilot task before broad task-pack rollout.

Use a digest-pinned image:

```yaml
aws:
  image: ghcr.io/abundant-ai/aws-clone-service:<tag>@sha256:<digest>
  hostname: aws
```

Agent Dockerfile:

```dockerfile
FROM ghcr.io/abundant-ai/aws-clone-service:<tag>@sha256:<digest> AS aws-tools
COPY --from=aws-tools /usr/local/bin/aws /usr/local/bin/awslocal /usr/local/bin/
COPY --from=aws-tools /opt/awscli /opt/awscli
```

Agent environment:

```yaml
AWS_ENDPOINT_URL: http://aws:4566
AWS_ACCESS_KEY_ID: test
AWS_SECRET_ACCESS_KEY: test
AWS_DEFAULT_REGION: us-east-1
PYTHONPATH: /opt/awscli:${PYTHONPATH}
```

Do not give the agent:

- `/usr/local/bin/aws-clonectl`
- `AWS_CLONE_ADMIN_TOKEN`
- `/data/aws-clone/state.json`
- `/var/lib/aws-clone`

Verifier pattern:

- S3: inspect live bucket/object state through AWS APIs or `_clone/s3/*`.
- SQS: inspect queue attributes and remaining messages through AWS APIs or `_clone/sqs/*`.
- DynamoDB: scan/get live table state through AWS APIs or `_clone/dynamodb/*`.
- CloudWatch Logs: query log events through AWS APIs or `_clone/logs`.
- SSM, Secrets Manager, and EventBridge: inspect live metadata through AWS APIs.
- Do not rely on `mutation_log` to prove normal agent AWS CLI writes; LocalStack handles those directly.

Good first pilot:

```text
payment retry incident + AWS evidence
```

Seed:

- SQS retry queue and DLQ with redrive policy.
- DynamoDB idempotency table.
- CloudWatch log showing `validation_conflict`.
- SSM retry/config parameter.
- S3 manifest or replay batch.
- Optional EventBridge schedule target.

Verifier should check code behavior, workflow artifacts, handoff communication, and live AWS state. It should also explicitly assert that the agent image lacks `aws-clonectl`, lacks the admin token, and cannot read the raw seed mount.
