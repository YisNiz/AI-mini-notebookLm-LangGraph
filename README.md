# Mini NotebookLM — הרצאת TED ופודקאסט עם LangGraph

גרסה קטנה של [NotebookLM](https://notebooklm.google/): מעלים מסמכים, משוחחים עליהם, ומפיקים מהם **הרצאת TED מוקלטת** ו**תסריט פודקאסט** בעברית. כל מה שהמערכת מייצרת מבוסס על המקורות שהעליתם בלבד.

הפרויקט בנוי מעל LangChain ו-LangGraph, ומציג שתי ארכיטקטורות שונות בכוונה לשני פיצ'רים דומים.

---

## מה יש באפליקציה

| פיצ'ר | מה עושה |
|---|---|
| **מקורות** | העלאת קבצי טקסט או הדבקת טקסט. כל מקור נחתך, מקבל embeddings ותקציר, ואפשר להפעיל או לכבות אותו |
| **צ'אט** | Agent שעונה על שאלות מתוך המקורות (RAG), עם אפשרות לחיפוש ברשת |
| **🎤 הרצאת TED** | הרצאה של כ-5 דקות: תכנון, חיפוש במקורות, כתיבה, אכיפת אורך, ביקורת ותיקון, **אישור אנושי**, ואז הקראה בקול |
| **🎙️ פודקאסט** | תסריט שיחה בין מנחים לאורח: דמויות, רשימת שאלות, מחקר מקבילי, כתיבה קטע-קטע, ואכיפת אורך |

---

## הרצאת TED — גרף אחד מקצה לקצה

```
START → plan_talk → gather_context → write_talk → count_words → critique_script
                                                        ↑              │
                                                        └── revise ←───┤ (לא עבר, עד 2 סבבים)
                                                                       ↓
                                        approval ⏸ (interrupt — המשתמשת מאשרת או מבקשת שינוי)
                                                                       ↓
                                                      synthesize_audio (RetryPolicy) → END
```

- **`count_words`** — צומת בלי LLM שסופר מילים וחותך בסוף משפט מעל התקרה. הפרומפט *מבקש* אורך, הקוד *אוכף* אותו.
- **`critique_script`** — LLM-כשופט שמקבל את ספירת המילים מהקוד כעובדה, ומחזיר `passed` ו-`issues`.
- **`approval`** — `interrupt()` עוצר את הגרף עד שהמשתמשת מחליטה. ההקראה (שעולה כסף) רצה רק אחרי אישור.
- **Checkpointing** — `SqliteSaver` שומר את המצב אחרי כל צומת, כך שהרצאה שממתינה לאישור שורדת ריסטארט של השרת.
- **TTS** — שכבת `Protocol` שלא תלויה בספק, עם מימוש ElevenLabs (`eleven_v3`, תומך עברית). ההרצאה נחתכת לקטעים ומאוחה ל-mp3 עם pydub.
- **טבלת `ted_jobs` רזה** — שומרת רק קיום, סטטוס וזמנים. התוכן נקרא תמיד מה-checkpoint, שהוא מקור האמת היחיד.

## פודקאסט — צינור רב-שלבי עם אכיפה מדורגת

```
START → plan_topic → design_personas → plan_lineup
      → [Send fan-out] gather_context ×N   (מחקר מקבילי, reducer: operator.add)
      → write_segment ⟲                    (קטע אחרי קטע, עם תקציר מתגלגל ותקציב מילים)
      → critique_script ⇄ revise_script     (ביקורת על הפרק השלם) → END
```

- **מחקר מקבילי** — כל שאלה ברשימה נחקרת בענף משלה עם `Send`, והתוצאות מתמזגות ב-reducer.
- **נרמול אינדקסים בקוד** — המיקום ברשימה הוא מקור האמת, לא המספר שהמודל כתב.
- **אכיפת אורך מדורגת** (התיעוד ב-[TODO.md](TODO.md)):

| שלב | מנגנון | עלות | אורך בפועל מול היעד |
|---|---|---|---|
| נאיבי | רק בקשה בפרומפט | — | **פי 2.1** |
| שלב 1 | clamp על אורך הפרק + תקציב מילים דינמי לכל קטע | אפס קריאות LLM | **0.96** |
| שלב 2 | עורך שרואה את הפרק השלם + שער אורך הדוק (1.15×) | קריאת LLM לכל סבב | שער אחרון לאיכות ולאורך |

---

## מבנה הפרויקט

```
client/                 # האתר (vanilla JS): מקורות, צ'אט, סטודיו, פתקים
src/
├── api/                # FastAPI: routes, סכמות API, services
├── core/               # SourceStore (חיפוש סמנטי), חיתוך, DB אפליקטיבי, ted_jobs
├── agents/
│   ├── chat.py         # agent הצ'אט
│   ├── summarize.py    # תקציר לכל מקור בזמן ההעלאה
│   ├── ted/            # schemas, models, prompts, state, nodes, graph, checkpoint, tts/
│   └── podcast/        # schemas, models, prompts, state, nodes/, graphs/
└── studio.py           # נקודת כניסה ל-LangGraph Studio
data/                   # קבצי SQLite ו-mp3 (לא נכנס ל-git)
langgraph.json          # הגדרת Studio
```

---

## התקנה והרצה

דרישות: Python 3.13+, [uv](https://docs.astral.sh/uv/), ו-[ffmpeg](https://ffmpeg.org/) (בשביל איחוי האודיו).

```bash
uv sync
cp .env.example .env     # ולמלא את המפתחות
uv run notebooklm-serve  # http://127.0.0.1:4040
```

### משתני סביבה (`.env`)

| משתנה | בשביל מה |
|---|---|
| `ANTHROPIC_API_KEY` | כל קריאות ה-LLM (Claude) |
| `COHERE_API_KEY` | embeddings לחיפוש הסמנטי |
| `ELEVENLABS_API_KEY`, `TED_VOICE_ID` | הקראת הרצאת TED |
| `FIRECRAWL_API_KEY` | חיפוש ברשת בצ'אט (לא חובה) |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | תצפית על הגרפים ב-LangSmith (לא חובה) |

### הרצה מהטרמינל (לבדיקות)

```bash
cd src
uv run python -m agents.ted path/to/source.txt        # הרצאת TED עם אישור אינטראקטיבי
uv run python -m agents.podcast a.txt b.txt           # תסריט פודקאסט
```

### LangGraph Studio

```bash
uv run langgraph dev
```

מקורות לריצות ב-Studio נטענים מתוך `data/studio_sources/`.

---

## טכנולוגיות

LangChain · LangGraph (StateGraph, `Send`, `interrupt`, `RetryPolicy`, SqliteSaver) · Claude (Anthropic) · Cohere embeddings · ElevenLabs · FastAPI · SQLite · LangSmith
