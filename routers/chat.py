from fastapi import APIRouter

from dependencies import get_current_model
from services import chat_service

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
    return await chat_service.rag_query(question, use_drive=use_drive, deep_think=deep_think)


@router.post("/chat-folder")
async def chat_folder(question: str, folder: str = None):
    """Ask a question, optionally limited to a specific folder."""
    from dependencies import get_llm_client, get_current_model
    from services.search_service import hybrid_search
    from datetime import datetime

    where = {"folder": folder} if folder else None
    docs, metas, _ = hybrid_search(question, n_results=3, where=where)

    context = "\n---\n".join(docs) if docs else "No documents found."

    model = get_current_model()
    response = get_llm_client().chat.completions.create(
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

    return {"reply": response.choices[0].message.content}


@router.post("/chat-mcp")
async def chat_mcp(question: str, folder_path: str = ".", use_drive: str = "false"):
    """Ask a question using MCP-style function calling."""
    result = await chat_service.run_mcp_query(
        question, use_drive.lower() in ("true", "1", "yes")
    )
    return result
