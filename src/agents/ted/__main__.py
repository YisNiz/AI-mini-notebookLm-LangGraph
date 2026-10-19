"""Dev runner: uv run python -m agents.ted notes.txt article.md"""
import sys
from pathlib import Path

from netfree_unstrict_ssl import unstrict_ssl
unstrict_ssl()

from dotenv import load_dotenv
load_dotenv()

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from core.store import store
from agents.ted.graph import build_ted_graph

for arg in sys.argv[1:]:
    path = Path(arg)
    store.add(name=path.name, content=path.read_text(encoding="utf-8"))
    print(f"loaded source: {path.name}")

graph = build_ted_graph(checkpointer=InMemorySaver())
config = {
    "configurable": {"thread_id": "test"},
    "recursion_limit": 25,
    "run_name": "ted-talk",
    "metadata": {"job_id": "test"},
}

result = graph.invoke({"job_id": "test"}, config)
while result.get("__interrupt__"):
    payload = result["__interrupt__"][0].value
    print(payload["script_he"])
    print(f"\n({payload['word_count']} מילים, {payload['revision_count']} תיקונים)")
    if payload["critique_notes"]:
        print("הערות המבקר:", payload["critique_notes"])

    answer = input("לאשר? (y = אישור / כל טקסט אחר = משוב לשינוי): ").strip()
    if answer.lower() == "y":
        resume = {"action": "approve"}
    else:
        resume = {"action": "revise", "feedback": answer}

    result = graph.invoke(Command(resume=resume), config)

print("ההרצאה אושרה — הגרף הסתיים.")
