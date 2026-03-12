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


def search_threads(query="", max_results=15):
    """
    Search Gmail threads (conversations).
    When query is empty, returns the most recent threads (browse mode).
    Returns list of dicts: {id, subject, from_name, from_email, date,
                            snippet, message_count, participants}.
    Returns None on failure.
    """
    service = _get_service()
    if not service:
        return None
    try:
        params = {"userId": "me", "maxResults": max_results}
        if query:
            params["q"] = query
        result = service.users().threads().list(**params).execute()
        thread_stubs = result.get("threads", [])
        if not thread_stubs:
            return []

        threads = []
        for stub in thread_stubs:
            thread = service.users().threads().get(
                userId="me", id=stub["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()
            messages = thread.get("messages", [])
            if not messages:
                continue
            # Subject from first message, date/from from last
            first_headers = _msg_headers(messages[0])
            last_headers = _msg_headers(messages[-1])
            from_name, from_email = _parse_from(last_headers.get("From", ""))

            # Collect unique participant names
            participants = []
            seen = set()
            for msg in messages:
                h = _msg_headers(msg)
                name, email = _parse_from(h.get("From", ""))
                display = name or email
                if display and display not in seen:
                    seen.add(display)
                    participants.append(display)

            threads.append({
                "id": thread["id"],
                "subject": first_headers.get("Subject", "(no subject)"),
                "from_name": from_name,
                "from_email": from_email,
                "date": last_headers.get("Date", ""),
                "snippet": thread.get("snippet", ""),
                "message_count": len(messages),
                "participants": participants,
            })
        return threads
    except Exception:
        logger.exception("Failed to search Gmail threads")
        return None


def get_thread_messages(thread_id):
    """
    Fetch all messages in a Gmail thread.
    Returns list of dicts: [{from_name, from_email, date, body}], or None.
    """
    service = _get_service()
    if not service:
        return None
    try:
        thread = service.users().threads().get(
            userId="me", id=thread_id, format="full",
        ).execute()
        result = []
        for msg in thread.get("messages", []):
            headers = _msg_headers(msg)
            from_name, from_email = _parse_from(headers.get("From", ""))
            body = _extract_plain_text(msg.get("payload", {}))
            result.append({
                "from_name": from_name,
                "from_email": from_email,
                "date": headers.get("Date", ""),
                "body": body or "(no text content)",
            })
        return result
    except Exception:
        logger.exception("Failed to fetch Gmail thread %s", thread_id)
        return None


def _msg_headers(msg):
    """Extract headers dict from a Gmail message resource."""
    return {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}


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
