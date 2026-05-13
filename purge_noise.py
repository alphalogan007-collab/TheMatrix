"""
Brain purge — remove all artificial categorization from mind:knowledge and guidance:corpus.
The brain categorizes itself. We only keep raw absorbed knowledge.

KEEP in guidance:corpus:   wiki:, quran_, web:, foundation:, seed:, master:
DELETE from guidance:corpus: synthesis:, and all UUID hex-hash prefixed entries

KEEP in mind:knowledge:   everything NOT starting with corpus:
DELETE from mind:knowledge: all corpus: prefixed keys (1592 noise entries)

Reset guidance:harvested to match the cleaned corpus.
"""
import redis, json
from collections import Counter

r = redis.Redis(
    host="mindai_redis",
    port=6379,
    password="e7338d82b9bcea35bcd2b35874b39c75",
    decode_responses=True
)

# ── 1. Purge corpus: noise from mind:knowledge ────────────────────────────────
mk_keys = r.hkeys("mind:knowledge")
mk_delete = [k for k in mk_keys if k.startswith("corpus:") or k.startswith("domain_seed")]

print(f"mind:knowledge: {len(mk_keys)} total, deleting {len(mk_delete)} corpus:/domain_seed entries")
if mk_delete:
    r.hdel("mind:knowledge", *mk_delete)
    print(f"  Deleted {len(mk_delete)} entries from mind:knowledge")

# ── 2. Purge synthetic garbage from guidance:corpus ───────────────────────────
# Keep only: wiki:, quran_, web:, foundation:, seed:, master:, file:, book:, 
#            topic:, product:mega:, wisdom_, angel_, revelation
KEEP_PREFIXES = ("wiki:", "quran_", "web:", "foundation:", "seed:", "master:", 
                 "mega:teaching", "angel_", "wisdom_")

corpus_keys = r.hkeys("guidance:corpus")
corpus_delete = []
for k in corpus_keys:
    keep = any(k.startswith(p) for p in KEEP_PREFIXES)
    if not keep:
        corpus_delete.append(k)

print(f"\nguidance:corpus: {len(corpus_keys)} total, deleting {len(corpus_delete)} synthetic entries")
if corpus_delete:
    # Delete in batches of 500
    for i in range(0, len(corpus_delete), 500):
        batch = corpus_delete[i:i+500]
        r.hdel("guidance:corpus", *batch)
    print(f"  Deleted {len(corpus_delete)} entries from guidance:corpus")

# ── 3. Rebuild guidance:harvested from what remains ───────────────────────────
remaining_corpus = set(r.hkeys("guidance:corpus"))
print(f"\nguidance:corpus after purge: {len(remaining_corpus)} entries")

# Clear and rebuild harvested set — so harvester re-processes clean entries
r.delete("guidance:harvested")
print("  guidance:harvested cleared — harvester will re-absorb clean corpus")

# ── 4. Final state ────────────────────────────────────────────────────────────
mk_remaining = r.hkeys("mind:knowledge")
mk_prefixes = Counter()
for k in mk_remaining:
    prefix = k.split(":")[0] if ":" in k else "text"
    mk_prefixes[prefix] += 1

print(f"\n=== mind:knowledge after purge: {len(mk_remaining)} entries ===")
for p, c in mk_prefixes.most_common(15):
    print(f"  {p}: {c}")

corpus_remaining = r.hkeys("guidance:corpus")
corpus_prefixes = Counter()
for k in corpus_remaining:
    prefix = k.split(":")[0] if ":" in k else "other"
    corpus_prefixes[prefix] += 1

print(f"\n=== guidance:corpus after purge: {len(corpus_remaining)} entries ===")
for p, c in corpus_prefixes.most_common():
    print(f"  {p}: {c}")
