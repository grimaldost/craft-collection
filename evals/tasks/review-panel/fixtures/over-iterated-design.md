# Where we are

We've spent five sessions designing the rate limiter for our API gateway. The
design I've talked myself into (the one I'm leaning toward shipping): a
**token-bucket per API key, stored in Redis**, refilled by a background job every
second, with a Lua script for atomic check-and-decrement on each request.

Alternatives we considered and dropped:
- sliding-window log — too much memory at our request volume;
- fixed-window counter — burst at the window boundary;
- per-node in-memory buckets — no coordination across nodes.

Constraints: ~50k requests/sec, 12 gateway nodes, limits must be consistent across
nodes, p99 added latency budget < 2 ms, and a node restart must not reset a user's
remaining quota.

Honestly I can't tell anymore if the Redis token-bucket is right or if I've just
worn a groove into it.
