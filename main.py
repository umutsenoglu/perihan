from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from dependencies import init_startup
from routers import chat, index, drive, settings, whatsapp

app = FastAPI(title="Perihan")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup_event():
    await init_startup()


app.include_router(chat.router)
app.include_router(index.router)
app.include_router(drive.router)
app.include_router(settings.router)
app.include_router(whatsapp.router)
