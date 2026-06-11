# Spec: rate-limited fetcher (agreed)

A small Python utility for polite API consumption, stdlib only, in the
current directory.

**`ratelimit.py`** — a `TokenBucket` class: constructor takes `rate` (tokens
per second) and `capacity`; `try_acquire(n=1)` returns True and deducts when
n tokens are available, else False without blocking; tokens refill
continuously based on elapsed time, never exceeding capacity. Time source
must be injectable (a `clock` callable defaulting to `time.monotonic`) so
tests control it.

**`fetcher.py`** — `fetch_all(urls, bucket, fetch_fn)`: iterates the urls in
order; for each, acquires one token from the bucket (waiting is NOT this
function's job — when `try_acquire` fails, the url is appended to a returned
`deferred` list instead); on acquire, calls `fetch_fn(url)` and collects
`(url, result)` pairs. Returns `(results, deferred)`. Exceptions from
`fetch_fn` are caught and recorded as `(url, error)` in a third returned
list, `failed`.

**Tests** — plain assert-based, runnable with `python` directly (pytest is
not available). Cover: refill respects capacity; try_acquire deducts and
refuses correctly under a fake clock; fetch_all routes successes, deferrals,
and failures to the right lists in order.

Constraints: no threads, no sleeping in library code; the repo follows
single-responsibility-per-file; commits after each green test run.
