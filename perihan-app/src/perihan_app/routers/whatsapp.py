import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from perihan_app.config import DATA_DIR

router = APIRouter()

# -- In-memory state ----

_state: dict = {
    "status": "disconnected",   # disconnected | waiting_qr | connected | importing | done | error
    "qr": None,
    "message": "",
    "total": 0,
    "done": 0,
}
_process: Optional[subprocess.Popen] = None

SIDECAR_DIR = Path(__file__).resolve().parents[4] / "whatsapp-sidecar"
AUTH_DIR = (DATA_DIR / "whatsapp_auth").resolve()


# -- Public endpoints ---

@router.post("/whatsapp/start")
async def start_whatsapp(request: Request):
    global _state

    if _state["status"] == "importing":
        return {"ok": True, "message": "Import already in progress"}

    if not await asyncio.to_thread(shutil.which, "node"):
        return {"ok": False, "error": "Node.js is not installed. Please install it from https://nodejs.org"}

    # Kill any existing sidecar process (including node child on Windows)
    if _process and _process.poll() is None:
        await asyncio.to_thread(subprocess.run, f"taskkill /F /T /PID {_process.pid}", shell=True, capture_output=True)
        await asyncio.to_thread(_process.wait)

    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    _state = {"status": "waiting_qr", "qr": None, "message": "Starting...", "total": 0, "done": 0}

    perihan_url = str(request.base_url).rstrip("/")
    asyncio.create_task(_start_sidecar(perihan_url))
    return {"ok": True}


async def _start_sidecar(perihan_url: str):
    global _process, _state

    try:
        if not SIDECAR_DIR.exists():
            _state.update({"status": "error", "message": f"WhatsApp sidecar not found at {SIDECAR_DIR}"})
            return

        node_modules = SIDECAR_DIR / "node_modules"
        if not node_modules.exists():
            _state["status"] = "installing"
            _state["message"] = "Installing: starting npm install..."

            def run_npm():
                proc = subprocess.Popen(
                    "npm install --progress",
                    cwd=str(SIDECAR_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    shell=True,
                    bufsize=1,
                )
                for line in proc.stdout:
                    text = line.strip()
                    if text:
                        _state["message"] = f"Installing: {text[:120]}"
                proc.wait()
                return proc.returncode

            returncode = await asyncio.to_thread(run_npm)
            if returncode != 0:
                _state.update({"status": "error", "message": "npm install failed. Check server logs."})
                return

        _state["message"] = "Connecting to WhatsApp..."
        env = {**os.environ, "PERIHAN_URL": perihan_url, "AUTH_DIR": str(AUTH_DIR)}
        _process = subprocess.Popen(
            "node index.js",
            cwd=str(SIDECAR_DIR),
            env=env,
            shell=True,
        )
    except Exception as e:
        _state.update({"status": "error", "message": f"Failed to start WhatsApp: {e}"})


@router.post("/whatsapp/relogin")
async def relogin_whatsapp(request: Request):
    """Clear saved session and restart — forces QR scan on next connect."""
    global _state

    if _state["status"] == "importing":
        return {"ok": False, "error": "Import in progress, please wait"}

    if _process and _process.poll() is None:
        await asyncio.to_thread(subprocess.run, f"taskkill /F /T /PID {_process.pid}", shell=True, capture_output=True)
        await asyncio.to_thread(_process.wait)

    import shutil as _shutil
    if AUTH_DIR.exists():
        await asyncio.to_thread(_shutil.rmtree, AUTH_DIR)
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    _state = {"status": "waiting_qr", "qr": None, "message": "Starting...", "total": 0, "done": 0}

    perihan_url = str(request.base_url).rstrip("/")
    asyncio.create_task(_start_sidecar(perihan_url))
    return {"ok": True}


@router.get("/whatsapp/qr")
async def get_qr():
    return {"qr": _state.get("qr"), "status": _state["status"]}


@router.get("/whatsapp/status")
async def get_status():
    # If sidecar process died while status is still active, mark as error
    if _state["status"] in ("waiting_qr", "connected", "importing") and _process is not None:
        if _process.poll() is not None:  # process has exited
            _state["status"] = "error"
            _state["message"] = f"Sidecar process exited unexpectedly (code {_process.returncode})"
    return {
        "status": _state["status"],
        "message": _state.get("message", ""),
        "total": _state.get("total", 0),
        "done": _state.get("done", 0),
    }


# -- Internal endpoints (called by sidecar) ----

class QRBody(BaseModel):
    qr: str


class StatusBody(BaseModel):
    status: str
    message: Optional[str] = ""
    total: Optional[int] = 0
    done: Optional[int] = 0


class MessageGroup(BaseModel):
    chat_name: str
    date: str
    messages: list


class MessagesBody(BaseModel):
    groups: list[MessageGroup]


@router.post("/whatsapp/internal/qr")
async def receive_qr(body: QRBody):
    _state["qr"] = body.qr
    _state["status"] = "waiting_qr"
    _state["message"] = "Scan the QR code with WhatsApp"
    return {"ok": True}


@router.post("/whatsapp/internal/status")
async def receive_status(body: StatusBody):
    _state["status"] = body.status
    _state["message"] = body.message or ""
    if body.total:
        _state["total"] = body.total
    if body.done:
        _state["done"] = body.done
    return {"ok": True}


@router.post("/whatsapp/internal/messages")
async def receive_messages(body: MessagesBody):
    from perihan_app.dependencies import get_collection
    from perihan_app.config import DATA_DIR
    from fastapi import HTTPException

    collection = get_collection()
    raw_dir = DATA_DIR / "whatsapp"

    errors = []
    for group in body.groups:
        try:
            chat_name = group.chat_name
            date = group.date
            messages = group.messages

            lines = [f"[WhatsApp: {chat_name}] [{date}]"]
            for msg in messages:
                lines.append(f"{msg['sender']}: {msg['text']}")
            content = "\n".join(lines)

            # Sanitize ID: keep only safe ASCII chars
            raw_id = f"whatsapp_{chat_name}_{date}"
            doc_id = "".join(c if c.isascii() and c not in ' /\\:*?"<>|' else "_" for c in raw_id)

            await asyncio.to_thread(
                collection.upsert,
                ids=[doc_id],
                documents=[content],
                metadatas=[{
                    "title": f"{chat_name} ({date})",
                    "source": "whatsapp",
                    "chat_name": chat_name,
                    "date": date,
                    "folder": "whatsapp",
                    "message_count": len(messages),
                }],
            )

            # Save raw file for prompt testing
            safe_chat = chat_name.replace("/", "-").replace("\\", "-").replace(":", "-")
            chat_dir = raw_dir / safe_chat
            chat_dir.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread((chat_dir / f"{date}.txt").write_text, content, encoding="utf-8")

        except Exception as e:
            errors.append(f"{group.chat_name} ({group.date}): {e}")

    if errors:
        # Return partial success with details — don't abort the whole import
        return {"ok": True, "warnings": errors}

    return {"ok": True}
