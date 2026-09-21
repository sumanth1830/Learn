# Daily Digest Pipeline — Agentic Design, Celery Tasks

## Celery Tasks Flow

### `generate_daily_digest_task()`

Generates the daily digest for the day. Runs at a scheduled time late
in the day, so that the day's articles have had time to accumulate
before summarizing. Invokes `_run_digest_generation()`.

### `retry_daily_digest_task()`

Does the same as `generate_daily_digest_task`, but can be invoked
manually when the scheduled digest generation fails.

### `_run_digest_generation()`

1. Verify whether a digest is already present for today — if so,
   return.
2. Otherwise, fetch the articles saved today.
3. Initialize the state with those articles.
4. Invoke the digest graph with the initial state.
5. On approval, save the digest to the database. If not approved, log
   and skip — no digest row is created for the day, and it stays
   without one unless `retry_daily_digest_task` is run manually later.
6. Log the node-wise cost and token breakdown to the database.

### `poll_pib_feed_task()`

Fetches the PIB feed — currently polled every 30 minutes. Only new
articles (not already present in the fetched set) get saved to the
database. A title slug is used to handle duplicates generated within
the last 48 hours; in some cases, multiple articles are published
within a short time interval, and the duplicates are revoked. The
title format is somewhat ambiguous, but the issuing authority and
published date are standard across the articles.