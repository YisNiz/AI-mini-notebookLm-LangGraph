from dataclasses import dataclass
from langchain_core.tools import tool
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.types import Command
from core.sources import format_docs
from dotenv import load_dotenv
import os
from firecrawl import Firecrawl
from core.store import SourceStore, store
load_dotenv()
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver


@dataclass
class Answer:
    text: str
    sources: list[str]


MODEL = "anthropic:claude-sonnet-4-6"
SYSTEM_PROMPT = """
You are a helpful notebook research assistant.

Language:
- Always answer in Hebrew.
- Be clear, concise, and accurate.

Answering:
- Answer general questions directly when possible.
- Use search_sources for information in indexed sources.
- Use list_sources and get_source to inspect existing sources.
- Use web research when external or current information is needed.
Web research (mandatory workflow whenever the user asks to search/research the web
or the answer needs external/current information):
1. Write at least 3 different search queries covering different angles of the topic.
2. Call search_web once per query.
3. Merge the results, drop duplicates, and choose the 2-4 most credible and relevant URLs.
4. Call scrape_web on EACH chosen URL. This indexes it into the knowledge base.
   (Use crawl_web only if a whole site is needed.)
5. Call search_sources to retrieve passages from the indexed pages.
6. Answer ONLY from what search_sources returned, and mention which sources you used.

Rules:
- search_web returns only titles and snippets. They are candidates, NOT evidence.
  Never answer from search_web results alone.
- Never skip step 4, even if the snippets look sufficient.
- If scraping fails, say so honestly and try another URL.

Accuracy:
- Never invent sources or claim a tool succeeded when it failed.
- Explain tool failures honestly.
- Distinguish supported facts from uncertainty.
"""



def answer(question: str, thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}

    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config=config,
    )

    if result.get("__interrupt__"):
        interrupt = result["__interrupt__"][0]
        print(interrupt.value)
        return {
            "pending_approval": True,
            "interrupt": interrupt.value,
            "thread_id": thread_id,
        }

    return {
        "pending_approval": False,
        "text": result["messages"][-1].text,
        "thread_id": thread_id,
    }


def resume(thread_id: str, decisions: list[dict]) -> dict:
    config = {"configurable": {"thread_id": thread_id}}

    result = agent.invoke(
        Command(resume={"decisions": decisions}),
        config=config,
    )

    interrupts = result.get("__interrupt__", [])

    if interrupts:
        interrupt = interrupts[0]
        return {
            "pending_approval": True,
            "interrupt": interrupt.value,
            "thread_id": thread_id,
        }

    messages = result.get("messages", [])
    last_message = messages[-1] if messages else None

    return {
        "pending_approval": False,
        "text": getattr(last_message, "text", "") or "",
        "thread_id": thread_id,
    }

def make_tools(store: SourceStore):
    
    @tool
    def search_web(query: str) -> str:
        """Search the web and return CANDIDATE sources (title, URL, snippet).
        Snippets are not evidence. After searching, choose the best URLs and
        call scrape_web on them to index their full content."""
        firecrawl = Firecrawl(
            api_key=os.getenv("FIRECRAWL_API_KEY")
        )

        results = firecrawl.search(query, limit=5)
        print(f"[SEARCH WEB] Retrieved {len(results.web or [])} web results")
        pages = results.web or []

        if not pages:
            return "No web results found."

        body = "\n\n".join(
        f"[{i}] Title: {p.title}\nURL: {p.url}\nDescription: {p.description or ''}"
        for i, p in enumerate(pages, 1))
    
        return body + "\n\nNEXT STEP: pick the best URLs (across all your searches) and call scrape_web on each."
    
    
    @tool
    def scrape_web(url: str) -> str:
        """Extract a web page and index its content as a source."""
        firecrawl = Firecrawl(
            api_key=os.getenv("FIRECRAWL_API_KEY")
        )

        page = firecrawl.scrape(url, formats=["markdown"])
        content = page.markdown or ""

        if not content.strip():
            return f"No content extracted from {url}"

        source = store.add(
            name=url,
            content=content,
        )
        print(f"[SCRAPE SUCCESS] Indexed source: {source.id} - {url}")
        return (
            f"Source indexed successfully.\n"
            f"ID: {source.id}\n"
            f"URL: {url}"
        )
    
    @tool
    def crawl_web(url: str) -> str:
        """Crawl a website and index the extracted pages as sources."""
        firecrawl = Firecrawl(
            api_key=os.getenv("FIRECRAWL_API_KEY")
        )

        result = firecrawl.crawl(
            url,
            limit=5,
            scrape_options={"formats": ["markdown"]},
        )

        indexed = 0

        for page in result.data or []:
            content = page.markdown or ""

            if not content.strip():
                continue

            source_url = (
                getattr(page.metadata, "source_url", None)
                or url
            )

            store.add(
                name=source_url,
                content=content,
            )
            indexed += 1

        return f"Indexed {indexed} pages from {url}"

    @tool
    def search_sources(query: str) -> str:
        """Find passages in the active sources that are relevant to a query."""
        docs = store.search(query=query)

        if not docs:
            return "No relevant documents found in the active sources"

        return format_docs(docs)

    @tool
    def list_sources() -> str:
        """List all available sources."""
        sources = store.list()

        return "\n".join(
            f"{source.id}: {source.name}"
            for source in sources
        )

    @tool
    def get_source(source_id: str) -> str:
        """Get a source by its ID."""
        source = store.get(source_id)

        if source is None:
            return "Source not found"

        return source.content

    return [
        search_sources,
        list_sources,
        get_source,
        search_web,
        scrape_web,
        crawl_web,
    ]

checkpointer = InMemorySaver()
agent = create_agent(
    model=MODEL,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
    tools=make_tools(store),
    # middleware=[HumanInTheLoopMiddleware(...)], 
)



