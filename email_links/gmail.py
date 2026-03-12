"""
Gmail API abstraction layer.

Mirrors documents/gdrive.py — reuses the same OAuth credentials.
Only this file imports the Gmail-specific Google API calls.
"""

import logging

logger = logging.getLogger(__name__)

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def is_available():
    """
    Return True if Gmail is usable: Drive must be connected AND the
    stored token must include the gmail.readonly scope.
    """
    from documents import gdrive
    if not gdrive.is_connected():
        return False
    return has_gmail_scope()


def has_gmail_scope():
    """Check whether the current credentials include the gmail.readonly scope."""
    from documents import gdrive
    creds = gdrive.get_credentials()
    if not creds:
        return False
    # google-auth stores granted scopes as a frozenset on the Credentials object
    granted = getattr(creds, "scopes", None) or []
    return GMAIL_SCOPE in granted


def _get_service():
    """Return a Gmail API v1 service object, or None."""
    from documents import gdrive
    creds = gdrive.get_credentials()
    if not creds:
        return None
    try:
        from googleapiclient.discovery import build
        return build("gmail", "v1", credentials=creds)
    except Exception:
        logger.exception("Failed to build Gmail service")
        return None


def search_messages(query="", max_results=15):
    """
    Search Gmail using the same query syntax as the Gmail search bar.
    Returns a list of dicts: {id, subject, from_name, from_email, date, snippet}.
    Returns None on failure.
    """
    service = _get_service()
    if not service:
        return None
    try:
        result = service.users().messages().list(
            userId="me", q=query, maxResults=max_results,
        ).execute()
        message_ids = result.get("messages", [])
        if not message_ids:
            return []

        messages = []
        for msg_stub in message_ids:
            msg = service.users().messages().get(
                userId="me", id=msg_stub["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            from_raw = headers.get("From", "")
            from_name, from_email = _parse_from(from_raw)
            messages.append({
                "id": msg["id"],
                "subject": headers.get("Subject", "(no subject)"),
                "from_name": from_name,
                "from_email": from_email,
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
            })
        return messages
    except Exception:
        logger.exception("Failed to search Gmail messages")
        return None


def get_plain_text_body(message_id):
    """
    Fetch the plain text body of a single Gmail message.
    Returns the text string, or None on failure.
    """
    service = _get_service()
    if not service:
        return None
    try:
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full",
        ).execute()
        return _extract_plain_text(msg.get("payload", {}))
    except Exception:
        logger.exception("Failed to fetch Gmail message body for %s", message_id)
        return None


def _extract_plain_text(payload):
    """Recursively extract text/plain content from a Gmail message payload."""
    import base64
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    # Recurse into multipart parts
    for part in payload.get("parts", []):
        text = _extract_plain_text(part)
        if text:
            return text
    return None


def _parse_from(from_header):
    """Parse 'Display Name <email@example.com>' into (name, email)."""
    import re
    match = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>', from_header)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    # Bare email
    if "@" in from_header:
        return "", from_header.strip()
    return from_header.strip(), ""
