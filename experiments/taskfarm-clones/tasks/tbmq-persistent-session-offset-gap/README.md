# TBMQ Persistent Session Offset Gap

This task packages a focused TBMQ incident from a TaskFarm Scout Accepted candidate. A persistent MQTT APPLICATION session has Kafka-backed QoS 1 records for the offline window, but reconnect processing commits past undelivered offsets.

The agent should inspect `/app/src`, the seeded Postgres tables, TicketVector ticket `TBMQ-320`, Slack evidence, and Grafana alert context. The correct repair is scoped to the replay planner and the two affected session gaps; unrelated duplicate PUBACK/DUP=0 and QoS0 rows are decoys.

Run verification with:

```bash
tests/test.sh
```
