# Reference read end-to-end: the `Idempotency-Key` HTTP header (condensed spec)

- **Purpose.** Let clients safely retry unsafe requests (POST/PATCH) without
  duplicating side effects.
- **Client behavior.** The client generates a unique key (recommended: a UUIDv4)
  and sends it in the `Idempotency-Key` request header.
- **Server behavior on replay.** The server persists the key together with a
  fingerprint of the request and the produced response. On a later request with
  the same key:
  - original still processing → return `409 Conflict`;
  - original completed → return the stored response verbatim, adding
    `Idempotent-Replayed: true`;
  - same key but a *different* request body → return `422 Unprocessable Entity`
    (reusing a key with a different payload is a client error).
- **Expiry.** Keys expire after a server-defined retention window (commonly 24h);
  after expiry a key may be reused.
- **Scope.** Keys are scoped per endpoint and per authenticated principal, never
  global.
- **Storage gotcha.** The key store must be durable and atomic on insert (an
  `INSERT ... ON CONFLICT` or equivalent), or a race can let two concurrent
  first-requests both process and double-charge.
