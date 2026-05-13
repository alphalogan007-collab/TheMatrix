import asyncio, json, sys, os
sys.path.insert(0, '/app')
os.environ.setdefault("REDIS_URL", "redis://:e7338d82b9bcea35bcd2b35874b39c75@redis:6379/0")

async def main():
    from app.api.routes_mind_ask import _redis, _load_all_knowledge, _load_guidance_tokens, _compute_iq
    r = await _redis()
    try:
        await r.delete("mind:iq:snapshot")  # force fresh calc
        entries = await _load_all_knowledge(r)
        g_tokens = await _load_guidance_tokens(r)
        iq = _compute_iq(entries, g_tokens)
        print(json.dumps(iq, indent=2))
        print(f"\n=== guidance token universe: {len(g_tokens)} tokens ===")
        print(f"=== mind entries: {len(entries)} ===")
    finally:
        await r.aclose()

asyncio.run(main())
