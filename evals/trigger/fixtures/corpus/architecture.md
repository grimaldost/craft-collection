# Architecture

The service has three layers:

- **API** — validates requests and maps them to commands.
- **Domain** — the ledger rules: a post debits one account and credits another,
  and the two legs must sum to zero.
- **Store** — an append-only event log; balances are a projection over it.

Requests flow API → Domain → Store; reads are served from the projection.
