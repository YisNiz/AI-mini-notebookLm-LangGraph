"""Entry point for `langgraph dev` / LangGraph Studio (see langgraph.json).

Studio runs the graph in its own process, so this module does that process's
setup — the same setup the app server and the CLI do in their entry points:
NetFree SSL before any API client is created, and sources in the in-memory
store (Studio's process starts with an empty one).
"""

from netfree_unstrict_ssl import unstrict_ssl
unstrict_ssl()

from pathlib import Path

from core.store import store
from agents.ted.graph import build_ted_graph_for_server  # noqa: F401  (referenced by langgraph.json)

# Drop .txt/.md files here to give Studio runs something to plan a talk from.
STUDIO_SOURCES = Path(__file__).resolve().parents[1] / "data" / "studio_sources"

for path in sorted(STUDIO_SOURCES.glob("*")):
    if path.suffix in {".txt", ".md"}:
        store.add(name=path.name, content=path.read_text(encoding="utf-8"))
