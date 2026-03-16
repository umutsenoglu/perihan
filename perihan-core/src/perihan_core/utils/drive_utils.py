import io
from pathlib import Path

from perihan_core.config import SUPPORTED_EXTENSIONS

_DRIVE_SKIP_MIME_PREFIXES = ("image/", "video/", "audio/")
_DRIVE_SKIP_MIME_EXACT = {
    "application/vnd.google-apps.photo",
    "application/vnd.google-apps.video",
    "application/vnd.google-apps.audio",
    "application/vnd.google-apps.shortcut",
    "application/vnd.google-apps.map",
    "application/vnd.google-apps.fusiontable",
}


def drive_read_content(svc, file_id: str, name: str, mime: str) -> str | None:
    """Download/export a Drive file and return its text content, or None if unsupported."""
    from googleapiclient.http import MediaIoBaseDownload
    from perihan_core.utils.file_reader import read_file_content

    EXPORT_MAP = {
        "application/vnd.google-apps.document": "text/plain",
        "application/vnd.google-apps.spreadsheet": "text/csv",
    }
    SKIP_PREFIXES = ("image/", "video/", "audio/")
    if any(mime.startswith(p) for p in SKIP_PREFIXES):
        return None
    try:
        if mime in EXPORT_MAP:
            content_bytes = svc.files().export(fileId=file_id, mimeType=EXPORT_MAP[mime]).execute()
            return content_bytes.decode("utf-8", errors="ignore")
        else:
            suffix = Path(name).suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                return None
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, svc.files().get_media(fileId=file_id))
            done = False
            while not done:
                _, done = downloader.next_chunk()
            tmp = Path(f"/tmp/gdrive_{file_id}{suffix}")
            tmp.write_bytes(buf.getvalue())
            content = read_file_content(tmp) or None
            tmp.unlink(missing_ok=True)
            return content
    except Exception:
        return None


def drive_list_all_files(svc, folder_id: str = "root", folder_path: str = "") -> list:
    """Recursively list all indexable (non-media, non-folder) files in a Drive folder tree."""
    files = []
    page_token = None
    while True:
        kwargs = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "nextPageToken, files(id,name,mimeType)",
            "pageSize": 100,
        }
        if page_token:
            kwargs["pageToken"] = page_token
        result = svc.files().list(**kwargs).execute()
        for f in result.get("files", []):
            mime = f["mimeType"]
            if mime == "application/vnd.google-apps.folder":
                sub_path = f"{folder_path}/{f['name']}" if folder_path else f["name"]
                files.extend(drive_list_all_files(svc, f["id"], sub_path))
            elif (
                any(mime.startswith(p) for p in _DRIVE_SKIP_MIME_PREFIXES)
                or mime in _DRIVE_SKIP_MIME_EXACT
            ):
                continue  # skip images, videos, audio
            else:
                files.append(
                    {
                        "id": f["id"],
                        "name": f["name"],
                        "mimeType": mime,
                        "folder_path": folder_path or "root",
                    }
                )
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return files
