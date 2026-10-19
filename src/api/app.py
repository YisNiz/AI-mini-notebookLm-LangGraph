"""The FastAPI application: REST endpoints + static web client.

Endpoints
    GET    /api/health
    
    Sources
        GET    /api/sources              list
        POST   /api/sources              add (paste text)
        POST   /api/sources/upload       add (file upload)
        GET    /api/sources/{id}         view full content
        PATCH  /api/sources/{id}         toggle active
        DELETE /api/sources/{id}         remove
    Chat
        POST   /api/chat                 grounded chat (engine + impl A/B)
    TED talk
        POST   /api/ted                  start a talk (runs until the approval gate)
        GET    /api/ted                  list talks
        GET    /api/ted/{id}             one talk (content from the checkpoint)
        POST   /api/ted/{id}/resume      approve / request changes / retry audio
        GET    /api/ted/{id}/audio       the talk's mp3
        DELETE /api/ted/{id}             delete talk + its graph thread
    Studio
        GET    /api/studio/artifacts     artifact kinds
        POST   /api/studio/generate      generate (501 until stage 3)
    Notes
        GET    /api/notes
        POST   /api/notes
        DELETE /api/notes/{id}

The web client (``client/``) is served as static files at ``/``.
"""

from __future__ import annotations

from netfree_unstrict_ssl import unstrict_ssl
unstrict_ssl()

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import services
from api.schemas import (
    AddNoteRequest,
    AddSourceRequest,
    ArtifactKind,
    ChatDecisionRequest,
    ChatRequest,
    ChatResponse,
    Note,
    SetActiveRequest,
    SourceDetail,
    SourceInfo,
    TedResumeRequest,
    TedTalk,
)

app = FastAPI(title="NotebookLM (LangChain learning project)")


@app.middleware("http")
async def no_store(request: Request, call_next):
    """Disable client caching so edits to the web client show up on a normal reload.

    StaticFiles otherwise lets the browser treat assets as "fresh" without revalidating,
    which makes CSS/JS changes appear not to take effect. Fine for this dev/learning app.
    """
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}



# -- sources -------------------------------------------------------------------


@app.get("/api/sources", response_model=list[SourceInfo])
def get_sources() -> list[SourceInfo]:
    return services.list_sources()


@app.post("/api/sources", response_model=SourceInfo)
def add_source(req: AddSourceRequest) -> SourceInfo:
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Source content is empty.")
    return services.add_source(req.name, req.content)


@app.post("/api/sources/upload", response_model=SourceInfo)
async def upload_source(file: UploadFile = File(...)) -> SourceInfo:
    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File must be UTF-8 text.") from exc
    if not content.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    return services.add_source(file.filename, content)


@app.get("/api/sources/{source_id}", response_model=SourceDetail)
def view_source(source_id: str) -> SourceDetail:
    source = services.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    return source


@app.patch("/api/sources/{source_id}", response_model=SourceInfo)
def toggle_source(source_id: str, req: SetActiveRequest) -> SourceInfo:
    source = services.set_source_active(source_id, req.active)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    return source


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: str) -> dict[str, bool]:
    if not services.remove_source(source_id):
        raise HTTPException(status_code=404, detail="Source not found.")
    return {"ok": True}


# -- chat ----------------------------------------------------------------------


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    return services.run_chat(req)

@app.post("/api/chat/decision", response_model=ChatResponse)
def chat_decision(req: ChatDecisionRequest) -> ChatResponse:
    return services.run_chat_decision(req)


# -- TED talk ------------------------------------------------------------------


@app.post("/api/ted", response_model=TedTalk)
def ted_start() -> TedTalk:
    try:
        return services.start_ted()
    except ValueError as exc:  # e.g. "No active sources ..."
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ted", response_model=list[TedTalk])
def ted_list() -> list[TedTalk]:
    return services.list_ted()


@app.get("/api/ted/{job_id}", response_model=TedTalk)
def ted_get(job_id: str) -> TedTalk:
    try:
        return services.get_ted(job_id)
    except services.TedNotFound as exc:
        raise HTTPException(status_code=404, detail="Talk not found.") from exc


@app.post("/api/ted/{job_id}/resume", response_model=TedTalk)
def ted_resume(job_id: str, req: TedResumeRequest) -> TedTalk:
    try:
        return services.resume_ted(job_id, req.action, req.feedback)
    except services.TedNotFound as exc:
        raise HTTPException(status_code=404, detail="Talk not found.") from exc


@app.get("/api/ted/{job_id}/audio")
def ted_audio(job_id: str) -> FileResponse:
    path = services.ted_audio_path(job_id)
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="Audio not ready.")
    return FileResponse(path, media_type="audio/mpeg", filename=f"ted-{job_id}.mp3")


@app.delete("/api/ted/{job_id}")
def ted_delete(job_id: str) -> dict[str, bool]:
    if not services.delete_ted(job_id):
        raise HTTPException(status_code=404, detail="Talk not found.")
    return {"ok": True}


# -- studio --------------------------------------------------------------------


@app.get("/api/studio/artifacts", response_model=list[ArtifactKind])
def studio_artifacts() -> list[ArtifactKind]:
    return services.list_artifacts()


@app.post("/api/studio/generate", response_model=Note)
def studio_generate(req: dict) -> Note:
    try:
        return services.generate_artifact(req.get("kind", ""), req.get("impl", "A"))
    except services.ComingSoon as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except services.GenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# -- notes ---------------------------------------------------------------------


@app.get("/api/notes", response_model=list[Note])
def get_notes() -> list[Note]:
    return services.list_notes()


@app.post("/api/notes", response_model=Note)
def add_note(req: AddNoteRequest) -> Note:
    return services.add_note(req.title, req.content)


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str) -> dict[str, bool]:
    if not services.remove_note(note_id):
        raise HTTPException(status_code=404, detail="Note not found.")
    return {"ok": True}


# Serve the web client. Mounted last so it only catches non-/api paths.

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CLIENT_DIR = PROJECT_ROOT / "client"
if _CLIENT_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_CLIENT_DIR), html=True), name="client")
