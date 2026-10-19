"""Dev runner: uv run python -m agents.podcast notes.txt article.md"""
import json
import sys
from pathlib import Path

from netfree_unstrict_ssl import unstrict_ssl
unstrict_ssl()

from dotenv import load_dotenv
load_dotenv()

from core.store import store
from agents.podcast.graphs.script_graph import build_script_graph

for arg in sys.argv[1:]:
    path = Path(arg)
    store.add(name=path.name, content=path.read_text(encoding="utf-8"))
    print(f"loaded source: {path.name}")

graph = build_script_graph()
final_state = None
for mode, chunk in graph.stream(
    {"job_id": "test"},
    config={
        "recursion_limit": 60,
        "max_concurrency": 2,
        "run_name": "podcast-script",
        "metadata": {"job_id": "test"},
    },
    stream_mode=["updates", "values"],
):
    if mode == "updates":
        for node in chunk:
            print(f">>> {node} done")
    else:
        final_state = chunk
result = final_state

for key in ("brief", "cast"):
    print(f"--- {key} ---")
    print(json.dumps(result[key].model_dump(), indent=2, ensure_ascii=False))
print("--- lineup ---")
print(json.dumps([i.model_dump() for i in result["lineup"]], indent=2, ensure_ascii=False))
print("--- research ---")
print(json.dumps([n.model_dump() for n in sorted(result.get("research", []), key=lambda n: n.item_index)], indent=2, ensure_ascii=False))
print("--- script ---")
for turn in result.get("turns") or []:
    print(f"{turn.speaker_name}: {turn.text_he}")
if result.get("critique"):
    print("--- critique ---")
    print("approved:", result["critique"].approved, "| revisions:", result.get("revision_count", 0))
    print(json.dumps(result["critique"].issues, indent=2, ensure_ascii=False))
