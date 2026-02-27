import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from dependencies import get_collection
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

    asyncio.create_task(asyncio.to_thread(build_global_vocab))
    return {"message": f"Indexed '{title}' in {len(chunks)} chunks"}


@router.post("/index-folder")
async def index_folder(folder_path: str):
    """Index all documents from a local folder recursively. Streams SSE progress events."""
    async def stream():
        async for event in index_service.index_local_folder(folder_path):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/index-gdrive")
async def index_gdrive(folder_id: str = "root"):
    """Index all Google Drive files into the local VectorDB. Streams SSE progress events."""
    async def stream():
        async for event in index_service.index_gdrive_files(folder_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
