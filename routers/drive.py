import os

from fastapi import APIRouter, HTTPException

from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE, GOOGLE_SCOPES
from dependencies import get_drive, get_gmail, load_drive_service

APP_BASE_URL: str = os.environ.get("APP_BASE_URL", "http://localhost:8000")

router = APIRouter()


@router.get("/drive/status")
async def drive_status():
    """Return whether Google Drive and Gmail are connected."""
    drive_connected = GOOGLE_TOKEN_FILE.exists() and get_drive() is not None
    gmail_connected = GOOGLE_TOKEN_FILE.exists() and get_gmail() is not None
    return {"connected": drive_connected, "gmail_connected": gmail_connected}


@router.get("/auth/google")
async def google_auth():
    """Step 1: Return the Google authorization URL for the user to visit."""
    from google_auth_oauthlib.flow import Flow

    if not GOOGLE_CREDENTIALS_FILE.exists():
        raise HTTPException(400, "credentials.json not found. Place it in the data/ folder.")
    flow = Flow.from_client_secrets_file(
        str(GOOGLE_CREDENTIALS_FILE),
        scopes=GOOGLE_SCOPES,
        redirect_uri=f"{APP_BASE_URL}/auth/google/callback",
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return {"auth_url": auth_url}


@router.get("/auth/google/callback")
async def google_callback(code: str):
    """Step 2: Exchange auth code for token, save to token.json."""
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        str(GOOGLE_CREDENTIALS_FILE),
        scopes=GOOGLE_SCOPES,
        redirect_uri=f"{APP_BASE_URL}/auth/google/callback",
    )
    flow.fetch_token(code=code)
    GOOGLE_TOKEN_FILE.write_text(flow.credentials.to_json())
    load_drive_service()  # warm up cache
    return {"message": "Google Drive connected successfully."}
