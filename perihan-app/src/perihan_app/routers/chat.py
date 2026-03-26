from fastapi import APIRouter, HTTPException

from perihan_app.dependencies import get_current_model, get_llm_client, get_collection, get_drive, get_gmail
from perihan_app.services.log_service import append_log
from perihan_core.services import chat_service
from perihan_core.services.chat_service import LLMError

router = APIRouter()


@router.get("/current-model")
async def get_current_model_endpoint():
    """Return the currently active LLM model name and provider."""
    model = get_current_model()
    provider = "gemini" if model.startswith("gemini-") else "ollama"
    return {"model": model, "provider": provider}


@router.post("/chat")
async def chat(question: str, use_drive: bool = True, deep_think: bool = False):
    """Ask a question across all documents. If deep_think=True and RAG is uncertain, falls back to MCP."""
    try:
        return await chat_service.rag_query(
            question, use_drive=use_drive, deep_think=deep_think, endpoint="/chat",
            collection=get_collection(), llm_client=get_llm_client(), model=get_current_model(),
            drive_svc=get_drive(), gmail_svc=get_gmail(), log_fn=append_log,
        )
    except LLMError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.post("/chat-folder")
async def chat_folder(question: str, folder: str = None):
    """Ask a question, optionally limited to a specific folder."""
    import asyncio
    from perihan_core.services.search_service import hybrid_search
    from datetime import datetime

    collection = get_collection()
    where = {"folder": folder} if folder else None
    docs, metas, _ = await asyncio.to_thread(
        hybrid_search, question, n_results=3, where=where, collection=collection
    )

    context = "\n---\n".join(docs) if docs else "No documents found."

    model = get_current_model()
    llm_client = get_llm_client()
    try:
        response = await asyncio.to_thread(
            llm_client.chat.completions.create,
            model=model,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": f"""
You are Perihan, a helpful document assistant.
Today's date is {datetime.now().strftime('%d %B %Y')}.
If the documents below contain relevant information, use them to answer.
Include the source file path when citing documents.
If the question is general and not covered in the documents, answer from your own knowledge.

Documents:
{context}
""",
                },
                {"role": "user", "content": question},
            ],
        )
    except Exception as e:
        from perihan_core.services.chat_service import _handle_llm_error
        llm_err = _handle_llm_error(e)
        raise HTTPException(status_code=llm_err.status_code, detail=str(llm_err))

    return {"reply": response.choices[0].message.content}


@router.post("/chat-mcp")
async def chat_mcp(question: str, folder_path: str = ".", use_drive: str = "false"):
    """Ask a question using MCP-style function calling."""
    import time

    start_time = time.perf_counter()
    model = get_current_model()
    use_drive_bool = use_drive.lower() in ("true", "1", "yes")
    try:
        result = await chat_service.run_mcp_query(
            question, use_drive_bool,
            llm_client=get_llm_client(), model=model,
            collection=get_collection(), drive_svc=get_drive(),
        )
        append_log({
            "endpoint": "/chat-mcp",
            "model": model,
            "question": question,
            "use_drive": use_drive_bool,
            "deep_think": False,
            "rag_results": [],
            "llm_prompt": None,
            "llm_response": result.get("reply"),
            "deep_think_triggered": False,
            "mcp_iterations": result.get("mcp_iterations", []),
            "error": None,
            "duration_ms": round((time.perf_counter() - start_time) * 1000),
        })
        return result
    except LLMError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        append_log({
            "endpoint": "/chat-mcp",
            "model": model,
            "question": question,
            "use_drive": use_drive_bool,
            "deep_think": False,
            "rag_results": [],
            "llm_prompt": None,
            "llm_response": None,
            "deep_think_triggered": False,
            "mcp_iterations": [],
            "error": str(e),
            "duration_ms": round((time.perf_counter() - start_time) * 1000),
        })
        raise
