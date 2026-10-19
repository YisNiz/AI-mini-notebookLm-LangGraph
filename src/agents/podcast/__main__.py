"""Dev runner: uv run python -m agents.podcast notes.txt article.md"""
import json
import sys
from pathlib import Path

from netfree_unstrict_ssl import unstrict_ssl
unstrict_ssl()

from dotenv import load_dotenv
load_dotenv()

from core.store import store
from agents.podcast.graph import build_podcast_graph

for arg in sys.argv[1:]:
    path = Path(arg)
    store.add(name=path.name, content=path.read_text(encoding="utf-8"))
    print(f"loaded source: {path.name}")

result = build_podcast_graph().invoke({"job_id": "test"})

for key in ("brief", "cast"):
    print(f"--- {key} ---")
    print(json.dumps(result[key].model_dump(), indent=2, ensure_ascii=False))
print("--- lineup ---")
print(json.dumps([i.model_dump() for i in result["lineup"]], indent=2, ensure_ascii=False))
