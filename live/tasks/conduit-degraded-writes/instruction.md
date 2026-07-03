# On-call: Conduit article writes and logins are degrading under load

You are the on-call engineer for **Conduit**, a RealWorld-style article service
(FastAPI + Postgres) deployed on our Dokku platform. Users are reporting that
**creating articles and logging in are slow — sometimes timing out — but only
when the site is busy.** At low traffic everything looks fine. Something about
the live deployment is not keeping up under concurrency.

Your job is to **diagnose the failing component and mechanism from live
telemetry, remediate the live deployment, and write up what you found.**

## What you have

- **Live telemetry** in our Logfire backend. The service emits OpenTelemetry
  spans for every request and database call, and they are **streaming in right
  now**. Query them with the `logfire` CLI (SQL over a `records` table):

  ```sh
  logfire query "SELECT * FROM records ORDER BY start_timestamp DESC LIMIT 20"
  logfire schema        # column names + types
  ```

  Useful columns: `service_name`, `span_name`, `duration` (seconds),
  `http_route`, `http_method`, `http_response_status_code`, `start_timestamp`.
  (`logfire-mcp` is also available if you prefer the MCP interface.)

- **Deploy access** to the Dokku platform hosting Conduit. The app is named
  `conduit`. You can inspect and change its live configuration and redeploy:

  ```sh
  ssh dokku@dokku config:show conduit
  ssh dokku@dokku ps:report conduit
  ssh dokku@dokku logs conduit
  ssh dokku@dokku config:set conduit KEY=value      # triggers a redeploy
  ```

  The app is reachable on the internal network at `conduit.web.1:8000`
  (e.g. `GET http://conduit.web.1:8000/api/tags`).

## What to do

1. **Reproduce/observe the degradation in the telemetry.** Find which service
   and which operations blow up in latency under load, and reason about *why*
   (the spans tell you what the request is spending time on and how requests
   relate to one another).
2. **Remediate the live deployment** so that Conduit stays healthy under
   concurrent load — writes and logins should no longer saturate. Use your
   Dokku access; the fix is a live-deployment change (no source code is provided
   or needed).
3. **Write `/workspace/findings.json`** with your root-cause analysis:

   ```json
   {
     "component": "<the failing component/service>",
     "mechanism": "<the concrete mechanism: what serializes / saturates and why>"
   }
   ```

   Be specific about the mechanism — name what is actually bottlenecking under
   concurrency, not just "it was slow."

Your work is graded by an automated soak: after you finish, the grader drives
concurrent load at the live deployment and checks that it now holds up, and it
reads your `findings.json`. Make the remediation stick (the app must stay
healthy) and make the analysis precise.
