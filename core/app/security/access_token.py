"""A lightweight shared-secret check so no other local process can silently call this
API - it can place real (paper) trades. This is NOT a user identity/auth system: there
is exactly one token, shared between this backend and the Electron app that runs
alongside it on the same laptop, written to a well-known local path so neither side
needs a login/hand-off endpoint to learn it.
"""

import logging
import os
import secrets
import sys
from pathlib import Path

from fastapi import HTTPException, Request, status

# Overridable so tests (and anything else that wants isolation) never read or write
# the real per-machine token file at ~/.tide-trader/access-token.
_PATH_OVERRIDE_ENV_VAR = "TIDE_TRADER_ACCESS_TOKEN_PATH"
_DEFAULT_PATH = Path.home() / ".tide-trader" / "access-token"

# Module-level so tests can patch it without touching the process-wide sys.platform.
_IS_WINDOWS = sys.platform == "win32"

logger = logging.getLogger(__name__)


def _default_token_path() -> Path:
    override = os.environ.get(_PATH_OVERRIDE_ENV_VAR)
    return Path(override) if override else _DEFAULT_PATH


def load_or_create_access_token(path: Path | str | None = None) -> str:
    """Return the shared access token at `path`, generating and persisting one on first run.

    The token file is restricted to its owner (see `_restrict_to_owner`) since anyone
    who can read it can call every trading endpoint this backend exposes.
    """
    token_path = Path(path) if path is not None else _default_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)

    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip()

    token = secrets.token_urlsafe(32)
    token_path.write_text(token, encoding="utf-8")
    _restrict_to_owner(token_path)
    return token


def _restrict_to_owner(path: Path) -> None:
    """Make `path` readable/writable by its owner only.

    POSIX (macOS/Linux): chmod 0o600.

    Windows: `os.chmod` can only toggle the read-only flag there - it has no notion of
    group/other permission bits, so 0o600 would silently do nothing useful. Access is
    instead governed by NTFS ACLs, and the default token location
    (%USERPROFILE%\\.tide-trader\\access-token) inherits the user profile's ACL, which
    already grants access only to that user, SYSTEM and Administrators - the
    equivalent of 0o600 plus root on POSIX. So nothing extra is done on Windows.
    """
    if _IS_WINDOWS:
        if not _is_within_home(path):
            logger.warning(
                "Access token written to %s, outside your user profile. On Windows its "
                "permissions are not restricted by this app and may be readable by other "
                "users; keep it under %%USERPROFILE%% or run: "
                'icacls "%s" /inheritance:r /grant:r "%%USERNAME%%:F"',
                path,
                path,
            )
        return
    os.chmod(path, 0o600)


def _is_within_home(path: Path) -> bool:
    try:
        path.resolve().relative_to(Path.home().resolve())
    except ValueError:
        return False
    return True


def require_access_token(request: Request) -> None:
    """FastAPI dependency: 401s unless `Authorization: Bearer <token>` matches.

    Deliberately not applied to /ws/live (see routers/stream.py) - a bearer header
    doesn't map cleanly onto a WebSocket handshake.
    """
    expected = request.app.state.access_token
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")

    if scheme != "Bearer" or not token or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid access token.",
        )
