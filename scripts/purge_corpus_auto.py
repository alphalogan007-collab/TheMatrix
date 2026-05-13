"""
Clean guidance:corpus of UUID-keyed entries whose CONTENT is corpus:auto:* garbage.
Also clean mind:knowledge of entries absorbed from those garbage entries.
"""
import os
import json
import redis
from urllib.parse import urlparse

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
p = urlparse(REDIS_URL)
password = p.password or "e7338d82b9bcea35bcd2b35874b39c75"
host = p.hostname or "redis"
port = p.port or 6379

r = redis.Redis(host=host, port=port, password=password, decode_responses=True)

print("=== BEFORE ===")
print("guidance:corpus:", r.hlen("guidance:corpus"))
print("mind:knowledge:", r.hlen("mind:knowledge"))

# --- Clean guidance:corpus ---
# Delete UUID-keyed entries whose content/title is corpus:auto:* junk
all_corpus = r.hgetall("guidance:corpus")
bad_corpus_keys = []
for key, val in all_corpus.items():
    # Named keys like foundation:*, seed:*, web:*, master:* are real — keep them
    if ":" in key and not key.startswith("foundation:") and not key.startswith("seed:") \
            and not key.startswith("web:") and not key.startswith("master:") \
            and not key.startswith("product:"):
        # This is a UUID or cross:* key — check its content
        try:
            entry = json.loads(val)
            content = entry.get("content", "") or entry.get("text", "")
            title = entry.get("title", "")
            source = entry.get("source", "")
            if (content.startswith("corpus:auto") or title.startswith("corpus:auto")
                    or title.startswith("corpus:cross") or content.startswith("corpus:cross")):
                bad_corpus_keys.append(key)
        except Exception:
            pass
    elif ":" not in key:
        # Pure UUID (no colons) — check content
        try:
            entry = json.loads(val)
            content = entry.get("content", "") or entry.get("text", "")
            title = entry.get("title", "")
            if (content.startswith("corpus:auto") or title.startswith("corpus:auto")
                    or title.startswith("corpus:cross")):
                bad_corpus_keys.append(key)
        except Exception:
            pass

print("\nBad corpus entries (corpus:auto content): " + str(len(bad_corpus_keys)))

if bad_corpus_keys:
    batch_size = 100
    for i in range(0, len(bad_corpus_keys), batch_size):
        batch = bad_corpus_keys[i:i+batch_size]
        r.hdel("guidance:corpus", *batch)
    print("Deleted from guidance:corpus: " + str(len(bad_corpus_keys)))

# --- Clean mind:knowledge ---
# Delete entries whose text starts with corpus:auto: (absorbed garbage)
all_knowledge = r.hgetall("mind:knowledge")
bad_knowledge_keys = []
for key, val in all_knowledge.items():
    try:
        entry = json.loads(val)
        text = entry.get("text", "")
        source = entry.get("source", "")
        if (text.startswith("corpus:auto") or text.startswith("corpus:cross")
                or source.startswith("corpus:auto")):
            bad_knowledge_keys.append(key)
    except Exception:
        pass

print("Bad mind:knowledge entries (corpus:auto text): " + str(len(bad_knowledge_keys)))

if bad_knowledge_keys:
    batch_size = 100
    for i in range(0, len(bad_knowledge_keys), batch_size):
        batch = bad_knowledge_keys[i:i+batch_size]
        r.hdel("mind:knowledge", *batch)
    print("Deleted from mind:knowledge: " + str(len(bad_knowledge_keys)))

print("\n=== AFTER ===")
print("guidance:corpus:", r.hlen("guidance:corpus"))
print("mind:knowledge:", r.hlen("mind:knowledge"))

