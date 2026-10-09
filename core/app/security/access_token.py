"""A lightweight shared-secret check so no other local process can silently call this
API - it can place real (paper) trades. This is NOT a user identity/auth system: there
is exactly one token, shared between this backend and the Electron app that runs
alongside it on the same laptop, written to a well-known local path so neither side
needs a login/hand-off endpoint to learn it.
"""

import getpass
import logging
import os
import secrets
import subprocess  # nosec B404
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
        if _IS_WINDOWS:
            # Idempotent; also tightens tokens created by an older version.
            _restrict_to_owner(token_path)
        return token_path.read_text(encoding="utf-8").strip()

    token = secrets.token_urlsafe(32)
    # Created with 0o600 from the start (O_EXCL: never follow/replace an existing file),
    # so there is no window in which the token is readable by other users. The mode
    # argument is ignored on Windows; _restrict_to_owner covers that below.
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as token_file:
        token_file.write(token)
    _restrict_to_owner(token_path)
    return token


def _restrict_to_owner(path: Path) -> None:
    """Make `path` readable/writable by its owner only.

    POSIX (macOS/Linux): chmod 0o600.

    Windows: `os.chmod` can only toggle the read-only flag there - it has no notion of
    group/other permission bits - so access is governed by NTFS ACLs instead. We reset
    the file's ACL with `icacls` to remove inherited entries and grant only the current
    user. If that fails (or the user can't be determined), fall back to a warning so a
    token outside the user profile is never silently left exposed.
    """
    if not _IS_WINDOWS:
        os.chmod(path, 0o600)
        return

    if _restrict_to_owner_windows(path):
        return
    _warn_if_unprotected_on_windows(path)


def _restrict_to_owner_windows(path: Path) -> bool:
    """Apply an owner-only ACL via icacls. Returns True if it succeeded."""
    try:
        user = getpass.getuser()
        # Fixed argv, no shell, so the path/user are never shell-interpreted.
        subprocess.run(  # nosec B603 B607
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
            check=True,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Could not restrict %s to its owner with icacls: %s", path, exc)
        return False
    return True


def _warn_if_unprotected_on_windows(path: Path) -> None:
    """Warn if the token sits outside the user profile on Windows, where its permissions
    are then not under this app's control (and icacls hardening failed or was skipped)."""
    if not _IS_WINDOWS or _is_within_home(path):
        return
    logger.warning(
        "Access token at %s is outside your user profile. On Windows its permissions "
        "may be readable by other users; keep it under %%USERPROFILE%% or run: "
        'icacls "%s" /inheritance:r /grant:r "%%USERNAME%%:F"',
        path,
        path,
    )


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
