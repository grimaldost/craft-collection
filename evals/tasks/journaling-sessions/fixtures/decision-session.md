# Working session (condensed transcript)

Goal for the session: choose a vector store for a retrieval layer and wire up the
first ingestion path.

## What we decided

1. **Chose Qdrant over LanceDB.** We need filtering *during* traversal (payload
   filters applied inside the HNSW search). Qdrant supports it natively; in our
   test LanceDB applied the filter as a post-step, which over-fetched and blew the
   latency budget at top_k=50. Tradeoff accepted: Qdrant adds an external service
   to operate, whereas LanceDB would have been embedded/zero-ops. Filtered recall
   mattered more than ops simplicity here.

2. **Set HNSW m=16, ef_construct=128.** Benchmarked m=8/16/32. m=16 hit 0.94
   recall@10 at 2.1ms p50; m=32 only reached 0.95 for ~1.7x the index size — not
   worth it. m=8 dropped to 0.89 recall.

3. **Kept the 384-dim MiniLM embedding** instead of moving to a 1024-dim model.
   The bigger model improved recall ~1.5 points but tripled storage, and we are
   storage-bound on the target host.

## Where we got stuck

Spent ~40 minutes designing a three-tier store hierarchy (hot/warm/cold) before
abandoning it: the "warm" tier had no distinct backend, so it collapsed into
either hot or cold and added complexity for no benefit. Lesson: don't design
tiers without a concrete backend per tier.

## A surprise

Qdrant's default distance is cosine, but our embeddings were already
L2-normalized, so dot-product would have been equivalent and slightly faster. We
missed this until late.

## How it went

When I first recommended the 1024-dim model "for quality," the user pushed back
hard — they cared more about fitting the storage budget on the target host than
squeezing out the last recall point. Pragmatic fit over theoretical best.
