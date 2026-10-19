# Mini NotebookLM — Grounded TED Talks & Podcasts with LangGraph

A compact, NotebookLM-style research assistant. Upload your own documents, chat with them, and turn them into a **narrated TED-style talk** or a **multi-speaker podcast script** in Hebrew — every output grounded strictly in the sources you provided.

The project is built on **LangChain** and **LangGraph**, and deliberately implements its two generation features with **two contrasting architectures**, so the trade-offs between them are visible in working code.

---

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Feature 1 — TED Talk Pipeline](#feature-1--ted-talk-pipeline)
- [Feature 2 — Podcast Pipeline](#feature-2--podcast-pipeline)
- [TED vs. Podcast — Design Comparison](#ted-vs-podcast--design-comparison)
- [Engineering Principles](#engineering-principles)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Running](#running)
- [API Reference](#api-reference)
- [Observability](#observability)
- [Tech Stack](#tech-stack)
- [Roadmap & Known Limitations](#roadmap--known-limitations)

---

## Features

| Feature | Description |
|---|---|
| **Sources** | Upload `.txt` / `.md` files or paste text. Each source is chunked, embedded (Cohere multilingual), and summarized once at upload time. Sources can be toggled active/inactive; only active sources are used anywhere. |
| **Grounded chat** | A tool-calling agent that answers from the active sources via semantic search (RAG), with optional web research (Firecrawl). |
| **🎤 TED Talk** | A ~5-minute Hebrew talk: planning → retrieval → writing → code-enforced length → LLM critique/revision loop → **human approval gate** → text-to-speech. Paused talks survive server restarts. |
| **🎙️ Podcast** | A conversation between one or two hosts and a guest: topic planning → persona design → question lineup → **parallel research** → segment-by-segment writing with a **dynamic word budget** → whole-episode critique/revision loop. |
| **Studio & Notes** | Studio cards trigger generation; results can be saved as notes. Podcast scripts render as structured dialogue. |

---

## Architecture Overview

The application is split into strictly one-directional layers:

```
client/  →  api/app.py  →  api/services.py  →  agents/*  →  core/*
(browser)    (HTTP routes)   (product logic)     (LLM graphs)  (store, search, DB)
```

- **`client/`** — a dependency-free vanilla JS front end (sources, chat, studio, notes, approval modal, audio player).
- **`api/`** — FastAPI. `schemas.py` is the public API contract; `services.py` translates requests into agent calls and is the only layer that talks to both the web and the agents.
- **`agents/`** — all LLM logic: the chat agent, the TED graph, and the podcast graphs. Agents know nothing about HTTP.
- **`core/`** — infrastructure shared by everything: the `SourceStore` (chunking, embeddings, filtered similarity search), source summaries, and the application SQLite database.

Because `core` never imports from `agents`, and `agents` never import from `api`, each new feature only *extends* the API and client — it never changes what already exists.

---

## Feature 1 — TED Talk Pipeline

A single LangGraph `StateGraph`, end to end:

```
START → plan_talk → gather_context → write_talk → count_words → critique_script
                                                       ↑               │
                                                       └─── revise ←───┤ not passed (max 2 rounds)
                                                                       ↓
                                       approval ⏸  interrupt() — the user approves or asks for changes
                                             │                         │
                                             └── changes → revise      ↓
                                                         synthesize_audio (RetryPolicy ×3) → END
```

| Node | LLM? | Responsibility |
|---|---|---|
| `plan_talk` | ✅ (Haiku) | Reads the source summaries and returns a structured `TalkBrief`: topic, hook, exactly 3 key points. Fails fast with an actionable error if no source is active. |
| `gather_context` | ❌ | Runs a semantic search per key point, de-duplicates passages, and stores them as context. Pure retrieval — no model call. |
| `write_talk` | ✅ (Sonnet) | Writes the full script as free-form prose (deliberately *not* structured output). The word budget is injected from code constants. |
| `count_words` | ❌ | Counts words and hard-trims at a sentence boundary above `HARD_CAP`. The prompt *asks* for a length; this node *enforces* it. |
| `critique_script` | ✅ (Sonnet) | LLM-as-judge returning `CritiqueResult {passed, issues}`. It receives the word count computed in code as a fact rather than counting itself. |
| `revise` | ✅ (Sonnet) | Rewrites according to the critic's issues and any human feedback; always loops back through `count_words`. |
| `approval` | ❌ | Human-in-the-loop gate built on `interrupt()`. No side effects before the interrupt, since the node re-runs on resume. |
| `synthesize_audio` | ❌ (TTS) | Splits the approved script into ~800-character sentence chunks, synthesizes each with ElevenLabs, and stitches them into one MP3 with pydub. Wrapped in `RetryPolicy(max_attempts=3)`. |

**Persistence.** A `SqliteSaver` checkpointer stores the full state after every node (`data/ted_checkpoints.sqlite`). A talk waiting for approval is just a row in that file: it can be resumed from a different process, after a restart. If audio synthesis fails after approval has already been consumed, `run_resume` detects that the pending node is `synthesize_audio` and re-runs only that node via `invoke(None)` — the script is never regenerated.

**Thin job table.** The app keeps a `ted_jobs` table with only `job_id`, `status`, and timestamps. Talk content is never copied there; it is always read from the checkpoint (`get_values`), which remains the single source of truth.

**Provider-agnostic TTS.** The graph depends on a `TTSProvider` `Protocol`, not on ElevenLabs directly. The ElevenLabs implementation uses `eleven_v3`, the provider's model with Hebrew support. The contract already accepts a list of `(text, voice_id)` lines, ready for multi-speaker audio.

---

## Feature 2 — Podcast Pipeline

```
START → plan_topic → design_personas → plan_lineup
      → [Send fan-out] gather_context × N          parallel research, merged by an operator.add reducer
      → write_segment ⟲                             one lineup item per iteration
      → critique_script ⇄ revise_script            review of the whole episode (max 2 rounds) → END
```

| Stage | Highlights |
|---|---|
| **`plan_topic`** | Produces a `TopicBrief` (topic, narrative angle, 3–5 arc beats, target minutes). `target_minutes` is **clamped in code** to 3–10. |
| **`design_personas`** | Designs one or two contrasting hosts and exactly one guest — all fictional, each with a backstory, connection to the topic, a distinct speaking style, and a gender for voice casting. |
| **`plan_lineup`** | Builds an ordered list of questions across fixed sections (`opening` → `deep_dive` → `outro`) with typed questions (`open`, `follow_up`, `challenge`, …) and per-item search queries. Item indexes are **re-numbered in code** — list position is the source of truth, not model output. |
| **`gather_context`** | Fanned out with `Send`: each lineup item is researched in its own parallel branch (`max_concurrency=2`). Results are appended through an `Annotated[list, operator.add]` reducer so concurrent writes never overwrite each other. Thin coverage is reported honestly instead of padded. |
| **`write_segment`** | A sequential loop that writes one item at a time, carrying a **rolling summary** plus the last 6 turns instead of the full script. Each segment receives a **dynamic word budget** derived from what remains of the episode budget, weighted by section. A safety net trims whole turns above 1.5× the budget. |
| **`critique_script` / `revise_script`** | The only stage that sees the whole episode, so it catches cross-segment repetition, broken continuity, pacing, and style drift. Total length is passed in as a computed fact, and a code override rejects any script more than 15% over target even if the model approves it. |

### Length enforcement, measured

The podcast was intentionally built naive first, measured, and then fixed in cost-ordered stages (decision log in [`TODO.md`](TODO.md)). Same sources, same pipeline:

| Stage | Mechanism | Extra LLM cost | Words vs. target |
|---|---|---|---|
| Naive | Length requested in prompts only | — | 2,339 vs. 1,120 → **2.1×** |
| Stage 1 | `target_minutes` clamp + dynamic per-segment word budget | none | 937 vs. 980 → **0.96×** |
| Stage 2 | Whole-episode critic + 1.15× length gate in code | one call per round | final quality and length gate |

---

## TED vs. Podcast — Design Comparison

| Aspect | TED Talk | Podcast |
|---|---|---|
| Graph shape | One graph, end to end | Script graph (audio graph planned separately) |
| Human approval | Inside the graph via `interrupt()` | At the application level (planned) |
| State persistence | Everything in the checkpoint; thin job table | Script stored as data in the app (planned) |
| Length control | Enforced in code from day one | Built naive, measured, then enforced in stages |
| Quality control | Writer ⇄ critic loop on a short script | Critic is the only stage that sees the whole episode |
| Concurrency | Sequential | `Send` fan-out for research |
| Speakers | Single narrator | Cast of personas with distinct styles |

---

## Engineering Principles

- **Prompts ask; code enforces.** Anything that must be correct — length, indexes, turn numbering, active-source filtering — is verified in Python, not trusted to the model.
- **Use an LLM only for judgment or language.** Retrieval, counting, and trimming are plain code: free, fast, and deterministic.
- **Structured output only where there is structure.** Plans and critiques are Pydantic schemas; prose is free text.
- **Facts flow into the judge.** Critics receive computed measurements instead of being asked to measure.
- **Fail early with actionable errors.** Missing sources are caught before any paid model call.
- **Cost is a design input.** Cheap models for planning, stronger models for writing and critique, bounded revision loops, and synthesis only after human approval.

---

## Project Structure

```
client/                      Vanilla JS web client (index.html, app.js, styles.css)
src/
├── app.py                   Placeholder entry point
├── studio.py                LangGraph Studio entry (NetFree SSL setup + demo sources)
├── api/
│   ├── app.py               FastAPI routes + static client mount
│   ├── schemas.py           Public API contract (Pydantic)
│   ├── services.py          Product logic: chat, sources, notes, TED jobs, podcast
│   └── serve.py             uvicorn entry point (notebooklm-serve)
├── core/
│   ├── store.py             SourceStore: chunk → embed → filtered similarity search
│   ├── sources.py           Chunking, passage formatting, source overview
│   ├── db.py                Application SQLite database (data/app.sqlite)
│   └── ted_jobs.py          Thin TED job table (status only)
└── agents/
    ├── chat.py              Grounded chat agent (create_agent + tools)
    ├── summarize.py         Per-source summary at upload time
    ├── ted/
    │   ├── schemas.py       TalkBrief, CritiqueResult
    │   ├── models.py        Role → model registry
    │   ├── prompts.py       All TED prompts
    │   ├── state.py         TedState + length constants
    │   ├── nodes.py         All TED nodes and routers
    │   ├── graph.py         Graph assembly (+ zero-arg factory for Studio)
    │   ├── checkpoint.py    SqliteSaver singleton
    │   ├── tts/             TTSProvider Protocol + ElevenLabs implementation
    │   ├── __init__.py      run_start / run_resume / get_values
    │   └── __main__.py      Interactive CLI runner
    └── podcast/
        ├── schemas.py       TopicBrief, Persona, LineupItem, ResearchNote, DialogueTurn, …
        ├── models.py        Role → model registry
        ├── prompts.py       All podcast prompts
        ├── state.py         PodcastState (with reducer) + GatherInput
        ├── format_utils.py  Prompt formatting + tag-aware Hebrew word count
        ├── nodes/           planning.py, context.py, writing.py, critique.py
        ├── graphs/          script_graph.py
        ├── __init__.py      run()
        └── __main__.py      CLI runner
data/                        SQLite files and generated audio (git-ignored)
langgraph.json               LangGraph Studio configuration
TODO.md                      Podcast length-enforcement decision log
PLAN.md                      Course progress plan
```

---

## Getting Started

### Prerequisites

- Python **3.13+**
- [uv](https://docs.astral.sh/uv/)
- [ffmpeg](https://ffmpeg.org/) on `PATH` (used by pydub to stitch audio)

### Install

```bash
git clone https://github.com/YisNiz/AI-mini-notebookLm-LangGraph.git
cd AI-mini-notebookLm-LangGraph
uv sync
cp .env.example .env
```

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | All LLM calls (Claude Haiku / Sonnet) |
| `COHERE_API_KEY` | ✅ | Multilingual embeddings for semantic search |
| `ELEVENLABS_API_KEY` | for audio | Text-to-speech |
| `TED_VOICE_ID` | for audio | ElevenLabs voice used for TED talks |
| `TTS_MODEL`, `TTS_STABILITY` | optional | Override `eleven_v3` / `0.35` |
| `FIRECRAWL_API_KEY` | optional | Web research in chat |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | optional | Tracing in LangSmith |
| `NOTEBOOKLM_HOST`, `NOTEBOOKLM_PORT` | optional | Server bind (default `127.0.0.1:4040`) |

---

## Running

### Web app

```bash
uv run notebooklm-serve
# → http://127.0.0.1:4040
```

Add one or more sources, then use the chat or the **TED Talk** / **Podcast** cards in the Studio panel. TED talks open an approval window with the script, word count, and critic notes; once approved, an audio player appears.

### Command line (development)

```bash
cd src
uv run python -m agents.ted    path/to/source.txt           # interactive approval in the terminal
uv run python -m agents.podcast path/to/a.txt path/to/b.txt # prints brief, cast, lineup, research, script, critique
```

### LangGraph Studio

```bash
uv run langgraph dev
```

Then open `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`. The Studio process has its own in-memory store; drop `.txt` / `.md` files into `data/studio_sources/` to give it material.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` / `POST` | `/api/sources` | List sources / add pasted text |
| `POST` | `/api/sources/upload` | Upload a UTF-8 text file |
| `GET` / `PATCH` / `DELETE` | `/api/sources/{id}` | View / toggle active / remove |
| `POST` | `/api/chat` | Grounded chat turn |
| `POST` | `/api/ted` | Start a TED talk (runs until the approval gate) |
| `GET` | `/api/ted` | List talks |
| `GET` | `/api/ted/{id}` | One talk (content read from its checkpoint) |
| `POST` | `/api/ted/{id}/resume` | `{"action": "approve" \| "revise", "feedback": "…"}` — also retries failed audio |
| `GET` | `/api/ted/{id}/audio` | The talk's MP3 |
| `DELETE` | `/api/ted/{id}` | Delete a talk and its graph thread |
| `GET` | `/api/studio/artifacts` | Studio cards |
| `POST` | `/api/studio/generate` | `{"kind": "podcast"}` → dialogue note |
| `GET` / `POST` / `DELETE` | `/api/notes` | Notes |

---

## Observability

With LangSmith enabled, every run is traced with a `run_name` (`ted-talk`, `podcast-script`) and its `job_id` in metadata. A typical TED run on a single short source takes about 90 seconds and costs roughly $0.15, most of it in the revision loop — the kind of measurement that drives decisions such as model choice per role and `MAX_REVISIONS`.

---

## Tech Stack

| Area | Tools |
|---|---|
| Orchestration | LangGraph — `StateGraph`, conditional edges, `Send`, reducers, `interrupt` / `Command`, `RetryPolicy`, `SqliteSaver` |
| LLM | LangChain, Anthropic Claude (Haiku 5.5 for planning and research, Sonnet 5.5 for writing and critique) |
| Retrieval | Cohere `embed-multilingual-v3.0`, LangChain `InMemoryVectorStore`, `RecursiveCharacterTextSplitter` |
| Audio | ElevenLabs `eleven_v3`, pydub, ffmpeg |
| Backend | FastAPI, uvicorn, Pydantic, SQLite |
| Tooling | uv, LangSmith, LangGraph Studio |

---

## Roadmap & Known Limitations

- **Podcast audio (in progress):** a shared multi-speaker TTS package, a separate audio graph with voice casting by persona gender, and an application-level approval flow with the script persisted in the database.
- **Podcast generation is synchronous** and its results live in memory; they do not survive a restart yet (TED talks do).
- **Sources are in memory** and are lost on restart; only TED checkpoints and job records persist.
- **Known trade-offs of the length safety net** (documented in `TODO.md`): trimming removes whole turns from the end of a segment, and the rolling summary is not updated after a trim.
