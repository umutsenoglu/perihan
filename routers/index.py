import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from dependencies import get_collection, get_llm_client, get_current_model, get_drive, get_gmail
from services import index_service
from config import CHUNK_SIZE

router = APIRouter()


@router.post("/index")
async def index_document(title: str, content: str):
    """Add a single document to the vector database."""
    from services.search_service import build_global_vocab

    collection = get_collection()
    words = content.split()
    chunks = []
    for i in range(0, len(words), CHUNK_SIZE):
        chunk = " ".join(words[i : i + CHUNK_SIZE])
        chunks.append(chunk)

    for i, chunk in enumerate(chunks):
        doc_id = f"{title}_{i}"
        collection.upsert(
            ids=[doc_id],
            documents=[chunk],
            metadatas=[{"title": title, "chunk": i}],
        )

    asyncio.create_task(asyncio.to_thread(build_global_vocab, collection))
    return {"message": f"Indexed '{title}' in {len(chunks)} chunks"}


@router.post("/index-folder")
async def index_folder(folder_path: str):
    """Index all documents from a local folder recursively. Streams SSE progress events."""
    collection = get_collection()
    llm_client = get_llm_client()
    model = get_current_model()

    async def stream():
        async for event in index_service.index_local_folder(
            folder_path, collection=collection, llm_client=llm_client, model=model
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/index-gdrive")
async def index_gdrive(folder_id: str = "root"):
    """Index all Google Drive files into the local VectorDB. Streams SSE progress events."""
    collection = get_collection()
    drive_svc = get_drive()
    llm_client = get_llm_client()
    model = get_current_model()

    async def stream():
        async for event in index_service.index_gdrive_files(
            folder_id, collection=collection, drive_svc=drive_svc,
            llm_client=llm_client, model=model,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/index-gmail")
async def index_gmail(max_threads: int = 500):
    """Index Gmail threads into the local VectorDB (summaries only). Streams SSE progress events."""
    collection = get_collection()
    gmail_svc = get_gmail()

    async def stream():
        async for event in index_service.index_gmail_threads(
            max_threads, collection=collection, gmail_svc=gmail_svc,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
