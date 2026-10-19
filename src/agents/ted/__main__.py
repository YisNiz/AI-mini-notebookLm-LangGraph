"""Dev runner: uv run python -m agents.ted notes.txt article.md"""
import sys
from pathlib import Path

from netfree_unstrict_ssl import unstrict_ssl
unstrict_ssl()

from dotenv import load_dotenv
load_dotenv()

from core.store import store
from agents.ted import run_resume, run_start

JOB_ID = "test"

for arg in sys.argv[1:]:
    path = Path(arg)
    store.add(name=path.name, content=path.read_text(encoding="utf-8"))
    print(f"loaded source: {path.name}")

payload = run_start(JOB_ID)
while payload:
    print(payload["script_he"])
    print(f"\n({payload['word_count']} מילים, {payload['revision_count']} תיקונים)")
    if payload["critique_notes"]:
        print("הערות המבקר:", payload["critique_notes"])

    answer = input("לאשר? (y = אישור / כל טקסט אחר = משוב לשינוי): ").strip()
    if answer.lower() == "y":
        resume = {"action": "approve"}
    else:
        resume = {"action": "revise", "feedback": answer}

    result = run_resume(JOB_ID, resume)
    payload = result["__interrupt__"][0].value if result.get("__interrupt__") else None

print("ההרצאה אושרה — הגרף הסתיים.")
