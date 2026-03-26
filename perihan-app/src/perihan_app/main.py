from pathlib import Path

import anyio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from perihan_app.dependencies import init_startup
from perihan_app.routers import chat, index, drive, settings, whatsapp

app = FastAPI(title="Perihan")

# Raise default threadpool limit from 40 to 200 so asyncio.to_thread()
# calls don't bottleneck under concurrent requests.
anyio.to_thread.current_default_thread_limiter().total_tokens = 200

_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(_STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.on_event("startup")
async def startup_event():
    await init_startup()


app.include_router(chat.router)
app.include_router(index.router)
app.include_router(drive.router)
app.include_router(settings.router)
app.include_router(whatsapp.router)


def run():
    """Entry point for `perihan` console script."""
    import uvicorn
    uvicorn.run("perihan_app.main:app", host="0.0.0.0", port=8000, reload=True)
