"""Backend services: translate API requests into the LangChain code.

This is the thin layer between the stable API contract and the per-stage implementations.
Source management and notes are product glue (in-memory); chat is powered by the stage-2
agent; Studio artifacts raise ``ComingSoon`` until structured output lands in stage 3.
"""

from __future__ import annotations

import uuid

from api.schemas import (
    ArtifactKind,
    ChatDecisionRequest,
    ChatRequest,
    TedTalk,
    ChatResponse,
    DialogueLine,
    Citation,
    Note,
    PendingAction,
    SourceDetail,
    SourceInfo,
)
from agents import chat
from agents import podcast as podcast_agent
from agents import ted
from core import ted_jobs
from core.store import store


class ComingSoon(Exception):
    """Raised for a product capability that is advertised but not wired up yet."""


class GenerationError(Exception):
    """Raised when an artifact can't be generated; the message tells the user what to do."""


# -- sources -------------------------------------------------------------------


def _to_info(source) -> SourceInfo:
    return SourceInfo(
        id=source.id, name=source.name, chars=len(source.content), active=source.active
    )


def list_sources() -> list[SourceInfo]:
    return [_to_info(s) for s in store.list()]


def get_source(source_id: str) -> SourceDetail | None:
    source = store.get(source_id)
    if source is None:
        return None
    return SourceDetail(
        id=source.id,
        name=source.name,
        chars=len(source.content),
        active=source.active,
        content=source.content,
    )


def add_source(name: str | None, content: str) -> SourceInfo:
    name = (name or "").strip() or _auto_name(content)
    return _to_info(store.add(name=name, content=content))


def set_source_active(source_id: str, active: bool) -> SourceInfo | None:
    source = store.set_active(source_id, active)
    return _to_info(source) if source else None


def remove_source(source_id: str) -> bool:
    return store.remove(source_id)


def _auto_name(content: str) -> str:
    first_line = content.strip().splitlines()[0] if content.strip() else "Pasted source"
    first_line = first_line.lstrip("# ").strip()
    return (first_line[:40] or "Pasted source") + ".txt"


# -- chat ----------------------------------------------------------------------

def run_chat(req: ChatRequest) -> ChatResponse:
    result = chat.answer(
        req.message,
        thread_id=req.thread_id or "default",
    )

    if result.get("pending_approval"):
        interrupt = result.get("interrupt") or {}
        requests = interrupt.get("action_requests", [])

        return ChatResponse(
            answer="הסוכן ממתין לאישור שלך לסריקת המקור.",
            pending_approval=True,
            pending_actions=[
                PendingAction(
                    name=action.get("name", ""),
                    url=action.get("args", {}).get(
                        "url",
                        action.get("url", ""),), 
                   description=action.get("description", ""),
                )
                for action in requests
            ],
            thread_id=result.get("thread_id"),
            engine="chat",
        )

    return ChatResponse(
        answer=result.get("text", ""),
        thread_id=result.get("thread_id"),
        engine="chat",
    )


# -- studio (artifacts) --------------------------------------------------------

ARTIFACTS: list[ArtifactKind] = [
    ArtifactKind(key="ted", title="TED Talk", icon="🎤", status="ready"),
    ArtifactKind(key="podcast", title="Podcast", icon="🎙️", status="ready"),
    ArtifactKind(key="infographic", title="Infographic", icon="📊", status="planned"),
    ArtifactKind(key="powerpoint", title="PowerPoint", icon="📑", status="planned"),
    ArtifactKind(key="summary", title="Summary", icon="📄", status="planned"),
    ArtifactKind(key="faq", title="FAQ", icon="❓", status="planned"),
]

_ARTIFACTS_BY_KEY = {a.key: a for a in ARTIFACTS}


def list_artifacts() -> list[ArtifactKind]:
    return ARTIFACTS


def generate_artifact(kind: str, impl: str) -> Note:
    if kind == "podcast":
        return _generate_podcast()
    # Artifact generation lands with structured output; until then it's "coming soon".
    artifact = _ARTIFACTS_BY_KEY.get(kind)
    title = artifact.title if artifact else "This artifact"
    raise ComingSoon(f"{title} generation is coming soon.")


def _generate_podcast() -> Note:
    """Run the podcast script graph synchronously and turn the result into a
    dialogue note. Naive on purpose: no persistence, no approval (module 4)."""
    if not store.active_ids():
        raise GenerationError("No active sources. Enable at least one source to generate a podcast.")

    result = podcast_agent.run(job_id=uuid.uuid4().hex[:8])
    turns = (result or {}).get("turns") or []
    if not turns:
        raise GenerationError("The podcast came back empty. Please try again.")

    lines = [DialogueLine(speaker_name=t.speaker_name, text=t.text_he) for t in turns]
    title = f"🎙️ {result['brief'].topic}"[:80]
    content = "\n\n".join(f"{line.speaker_name}: {line.text}" for line in lines)
    note = Note(
        id=uuid.uuid4().hex[:8],
        title=title,
        content=content,
        content_type="dialogue",
        dialogue=lines,
    )
    _NOTES[note.id] = note
    return note


# -- notes ---------------------------------------------------------------------

_NOTES: dict[str, Note] = {}


def list_notes() -> list[Note]:
    return list(_NOTES.values())


def add_note(title: str, content: str) -> Note:
    note = Note(id=uuid.uuid4().hex[:8], title=title.strip() or "Untitled note", content=content)
    _NOTES[note.id] = note
    return note


def remove_note(note_id: str) -> bool:
    return _NOTES.pop(note_id, None) is not None


def run_chat_decision(req: ChatDecisionRequest) -> ChatResponse:
    result = chat.resume(
        thread_id=req.thread_id,
        decisions=[
            {"type": decision}
            for decision in req.decisions
        ],
    )

    if result.get("pending_approval"):
        interrupt = result.get("interrupt") or {}
        requests = interrupt.get("action_requests", [])

        return ChatResponse(
            answer="הסוכן ממתין לאישור שלך לסריקת המקור.",
            pending_approval=True,
            pending_actions=[
                PendingAction(
                    name=action.get("name", ""),
                    url=action.get("args", {}).get(
                    "url",
                    action.get("url", ""),
                    ),
                    description=action.get("description", ""),
                )
                for action in requests
            ],
            thread_id=result.get("thread_id"),
            engine="chat",
        )

    return ChatResponse(
        answer=result.get("text", ""),
        thread_id=result.get("thread_id"),
        engine="chat",
    )


# -- TED talk ------------------------------------------------------------------
# The graph (agents/ted) does the work; ted_jobs only tracks existence + status.
# Talk content is always read from the graph checkpoint via ted.get_values.


class TedNotFound(Exception):
    pass


def _ted_view(job: dict, payload: dict | None = None, error: str | None = None) -> TedTalk:
    """Merge the job row (status) with the talk content from the checkpoint."""
    values = ted.get_values(job["job_id"])
    brief = values.get("brief")
    critique = values.get("critique")
    payload = payload or {}
    return TedTalk(
        job_id=job["job_id"],
        status=job["status"],
        created_at=job.get("created_at"),
        topic=payload.get("topic") or (brief.topic if brief else None),
        script_he=payload.get("script_he") or values.get("script_he"),
        word_count=payload.get("word_count") or values.get("word_count"),
        revision_count=payload.get("revision_count", values.get("revision_count")),
        critique_notes=payload.get("critique_notes") or (critique.issues if critique else []),
        error=error,
    )


def start_ted() -> TedTalk:
    """Create a job and run the graph until the approval interrupt."""
    job_id = uuid.uuid4().hex[:12]
    ted_jobs.create(job_id)
    try:
        payload = ted.run_start(job_id)
    except Exception:
        ted_jobs.delete(job_id)  # nothing worth keeping (e.g. no active sources)
        raise
    return _ted_view(ted_jobs.get(job_id), payload)


def list_ted() -> list[TedTalk]:
    return [_ted_view(job) for job in ted_jobs.list_all()]


def get_ted(job_id: str) -> TedTalk:
    job = ted_jobs.get(job_id)
    if job is None:
        raise TedNotFound(job_id)
    return _ted_view(job)


def resume_ted(job_id: str, action: str, feedback: str | None) -> TedTalk:
    """Approve or request changes. Also serves as "retry" after a failed audio
    step: run_resume falls back to invoke(None) when no interrupt is pending."""
    if ted_jobs.get(job_id) is None:
        raise TedNotFound(job_id)
    try:
        result = ted.run_resume(job_id, {"action": action, "feedback": feedback})
    except Exception as exc:
        ted_jobs.set_status(job_id, ted_jobs.FAILED)
        return _ted_view(ted_jobs.get(job_id), error=str(exc))

    if result.get("__interrupt__"):
        ted_jobs.set_status(job_id, ted_jobs.PENDING_APPROVAL)
        return _ted_view(ted_jobs.get(job_id), result["__interrupt__"][0].value)
    ted_jobs.set_status(job_id, ted_jobs.AUDIO_READY)
    return _ted_view(ted_jobs.get(job_id))


def ted_audio_path(job_id: str) -> str | None:
    if ted_jobs.get(job_id) is None:
        return None
    return ted.get_values(job_id).get("audio_path")


def delete_ted(job_id: str) -> bool:
    return ted_jobs.delete(job_id)
