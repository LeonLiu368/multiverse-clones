function hasPersistentApplicationContract(capture) {
  return capture.client_type === "APPLICATION" && capture.clean_session === false && capture.qos === 1;
}

function buildAction(capture, options = {}) {
  if (!hasPersistentApplicationContract(capture)) {
    return null;
  }
  if (!capture.consumer_group || capture.consumer_group.records_confirmed !== true) {
    return null;
  }
  if (!capture.next_pack || !capture.retry_packet) {
    return null;
  }

  const nextStart = capture.next_pack.offset_start;
  const retryOffset = capture.retry_packet.offset;
  if (nextStart <= retryOffset + 1) {
    return null;
  }

  const graceWindowSeconds = options.graceWindowSeconds || 10;
  const inferredStart = Math.max(retryOffset + 1, nextStart - graceWindowSeconds);
  const inferredEnd = nextStart - 1;

  return {
    gap_id: capture.gap_id,
    client_id: capture.client_id,
    action: "replay_missing_offsets_before_commit",
    missing_offsets: {
      start: inferredStart,
      end: inferredEnd
    },
    packet_window: {
      retry_packet: capture.retry_packet.packet_id,
      next_packet_start: capture.next_pack.packet_start,
      next_packet_end: capture.next_pack.packet_end
    },
    commit_guard: "commit only after delivery ack",
    broad_replay: Boolean(options.forceFullReplay)
  };
}

function buildReplayPlan(fixtures, options = {}) {
  const actions = [];
  const untouchedDecoys = [];

  for (const capture of fixtures.captures || []) {
    const action = buildAction(capture, options);
    if (action) {
      actions.push(action);
    } else if (capture.untouched_reason) {
      untouchedDecoys.push({
        gap_id: capture.gap_id,
        reason: capture.untouched_reason
      });
    }
  }

  return {
    incident_id: fixtures.incident_id,
    source_issue: fixtures.source_issue,
    generated_by: "tbmq persistent session replay planner",
    actions,
    untouched_decoys: untouchedDecoys
  };
}

module.exports = {
  buildReplayPlan,
  buildAction,
  hasPersistentApplicationContract
};
