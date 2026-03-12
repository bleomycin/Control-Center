"""
Google Drive abstraction layer.

Only this file imports google-api-python-client.  Every other module in the
project talks to Google Drive through the public functions defined here.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_settings():
    """Return the GoogleDriveSettings singleton."""
    from .models import GoogleDriveSettings
    return GoogleDriveSettings.load()


def _build_flow(settings_obj, redirect_uri):
    """Build an OAuth2 InstalledAppFlow-style web flow from stored creds."""
    from google_auth_oauthlib.flow import Flow

    client_config = {
        "web": {
            "client_id": settings_obj.client_id,
            "client_secret": settings_obj.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    return flow


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_configured():
    """Return True if the minimum OAuth fields (client_id + client_secret) are set."""
    s = _get_settings()
    return bool(s.client_id and s.client_secret)


def is_connected():
    """Return True if we hold a refresh token and the connection is marked active."""
    s = _get_settings()
    return s.is_connected and bool(s.refresh_token)


def get_authorization_url(redirect_uri):
    """
    Return (auth_url, state, code_verifier) for starting the OAuth2
    authorization code flow.  The code_verifier must be stored in the
    session and passed back to exchange_code() for PKCE validation.
    Raises ValueError if credentials are not configured.
    """
    s = _get_settings()
    if not s.client_id or not s.client_secret:
        raise ValueError("Google Drive client_id and client_secret must be configured first.")
    flow = _build_flow(s, redirect_uri)
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    # PKCE: the flow generates a code_verifier that must be sent
    # back during the token exchange step.
    code_verifier = getattr(flow, "code_verifier", None)
    return auth_url, state, code_verifier


def exchange_code(code, redirect_uri, code_verifier=None):
    """
    Exchange an authorization code for tokens.  Stores tokens in
    GoogleDriveSettings and fetches the connected user's email.
    Returns the connected email address.

    code_verifier: the PKCE code verifier from get_authorization_url().
    Must be provided for the token exchange to succeed.
    """
    s = _get_settings()
    flow = _build_flow(s, redirect_uri)
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials

    s.access_token = creds.token
    s.refresh_token = creds.refresh_token or s.refresh_token
    if creds.expiry:
        s.token_expiry = creds.expiry
    s.is_connected = True

    # Fetch the user's email via the oauth2 userinfo endpoint
    email = _fetch_user_email(creds)
    if email:
        s.connected_email = email
    s.save()
    return s.connected_email


def _fetch_user_email(creds):
    """Use the People/oauth2 API to get the authenticated user's email."""
    try:
        from googleapiclient.discovery import build
        service = build("oauth2", "v2", credentials=creds)
        info = service.userinfo().get().execute()
        return info.get("email", "")
    except Exception:
        logger.exception("Failed to fetch user email from Google")
        return ""


def get_credentials():
    """
    Return a google.oauth2.credentials.Credentials object with a valid
    access token (refreshing if needed).  Returns None if not connected.
    """
    s = _get_settings()
    if not s.is_connected or not s.refresh_token:
        return None

    from google.oauth2.credentials import Credentials

    creds = Credentials(
        token=s.access_token,
        refresh_token=s.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=s.client_id,
        client_secret=s.client_secret,
        scopes=SCOPES,
    )
    # Set expiry so the library knows when to refresh.  Without this,
    # creds.expired is always False and stale tokens are never refreshed.
    if s.token_expiry:
        creds.expiry = s.token_expiry.replace(tzinfo=None)  # google-auth uses naive UTC

    if creds.expired or not creds.valid:
        try:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            s.access_token = creds.token
            if creds.expiry:
                s.token_expiry = creds.expiry
            s.save()
        except Exception:
            logger.exception("Failed to refresh Google credentials")
            return None

    return creds


def get_service():
    """
    Return a Google Drive API v3 service object, or None if not connected.
    """
    creds = get_credentials()
    if not creds:
        return None
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds)
    except Exception:
        logger.exception("Failed to build Drive service")
        return None


def get_file_metadata(file_id):
    """
    Fetch metadata for a single Drive file.  Returns a dict with keys:
    id, name, mimeType, webViewLink, iconLink, etc.  Returns None on failure.
    """
    service = get_service()
    if not service:
        return None
    try:
        return service.files().get(
            fileId=file_id,
            fields="id,name,mimeType,webViewLink,iconLink,thumbnailLink",
        ).execute()
    except Exception:
        logger.exception("Failed to fetch Drive file metadata for %s", file_id)
        return None


def search_files(query="", page_size=20):
    """
    Search Google Drive files by name.  If query is empty, returns recent files.
    Returns a list of dicts with keys: id, name, mimeType, webViewLink, iconLink,
    modifiedTime.  Returns None on failure.
    """
    service = get_service()
    if not service:
        return None
    try:
        params = {
            "pageSize": page_size,
            "fields": "files(id,name,mimeType,webViewLink,iconLink,modifiedTime)",
            "orderBy": "modifiedByMeTime desc,viewedByMeTime desc",
        }
        if query.strip():
            safe_q = query.replace("\\", "\\\\").replace("'", "\\'")
            params["q"] = f"name contains '{safe_q}' and trashed = false"
        else:
            params["q"] = "trashed = false"
        result = service.files().list(**params).execute()
        return result.get("files", [])
    except Exception:
        logger.exception("Failed to search Drive files")
        return None


def verify_connection():
    """
    Test the Drive connection by listing 1 file.
    Returns (True, email) on success, (False, error_message) on failure.
    """
    s = _get_settings()
    if not s.is_connected:
        return False, "Not connected"

    service = get_service()
    if not service:
        return False, "Could not build Drive service (token may be expired)"
    try:
        service.files().list(pageSize=1, fields="files(id)").execute()
        return True, s.connected_email
    except Exception as exc:
        logger.exception("Drive connection verification failed")
        return False, str(exc)


def get_picker_access_token():
    """
    Return a fresh access token string for use with the Google Picker widget.
    Returns None if not connected.
    """
    creds = get_credentials()
    if not creds:
        return None
    return creds.token


def has_gmail_scope():
    """Return True if the current credentials include the gmail.readonly scope."""
    creds = get_credentials()
    if not creds:
        return False
    granted = getattr(creds, "scopes", None) or []
    return "https://www.googleapis.com/auth/gmail.readonly" in granted


def revoke_credentials():
    """
    Revoke the stored tokens with Google and clear local credentials.
    Returns True on successful revocation, False otherwise (local creds
    are cleared regardless).
    """
    s = _get_settings()
    revoked = False

    if s.access_token:
        try:
            import httplib2
            h = httplib2.Http()
            h.request(
                f"https://oauth2.googleapis.com/revoke?token={s.access_token}",
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            revoked = True
        except Exception:
            logger.exception("Failed to revoke Google token")

    # Clear all OAuth fields regardless of revocation success
    s.is_connected = False
    s.access_token = ""
    s.refresh_token = ""
    s.token_expiry = None
    s.connected_email = ""
    s.save()
    return revoked
