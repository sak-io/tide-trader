"""A lightweight shared-secret check so no other local process can silently call this
API - it can place real (paper) trades. This is NOT a user identity/auth system: there
is exactly one token, shared between this backend and the Electron app that runs
alongside it on the same laptop, written to a well-known local path so neither side
needs a login/hand-off endpoint to learn it.
"""

import csv
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

    # A few attempts: two backends starting at once can race on creation, and a file left
    # empty by a crash between create and write is discarded and regenerated.
    for _ in range(3):
        existing = _read_token(token_path)
        if existing:
            if _IS_WINDOWS:
                # Idempotent; also tightens tokens created by an older version.
                _restrict_to_owner(token_path)
            return existing
        token_path.unlink(missing_ok=True)

        token = secrets.token_urlsafe(32)
        try:
            _create_token_file(token_path, token)
        except FileExistsError:
            continue  # lost the race; read the winner's token on the next pass
        return token

    raise RuntimeError(f"Could not create or read the access token at {token_path}")


def _read_token(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _create_token_file(path: Path, token: str) -> None:
    # Created with 0o600 from the start (O_EXCL: never follow/replace an existing file),
    # so there is no window in which the token is readable by other users. The mode
    # argument is ignored on Windows; _restrict_to_owner covers that below.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as token_file:
            token_file.write(token)
    except BaseException:
        path.unlink(missing_ok=True)  # never leave an empty token behind
        raise
    _restrict_to_owner(path)


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


def parse_icacls_principals(output: str, path: str) -> list[str]:
    """Principal names in `icacls <path>` output, e.g. ['NT AUTHORITY\\SYSTEM', 'HOST\\bob'].

    The first entry shares a line with the path (and the path usually contains the
    username), so the path is stripped before the principal is read.
    """
    principals = []
    for line in output.splitlines():
        if ":(" not in line:
            continue
        entry = line.strip()
        if entry.startswith(path):
            entry = entry[len(path) :].strip()
        principals.append(entry.rsplit(":(", 1)[0].strip())
    return principals


def _windows_identity() -> tuple[str, str]:
    """The current user's (DOMAIN\\name, SID), from `whoami /user`. The SID is what we
    grant to: unambiguous for local, domain and Azure AD accounts."""
    result = subprocess.run(  # nosec B603 B607
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    name, sid = next(csv.reader([result.stdout.strip()]))[:2]
    if not sid.startswith("S-1-"):
        raise ValueError(f"unexpected SID from whoami: {sid!r}")
    return name, sid


def _icacls(*args: str, capture_text: bool = False) -> str:
    # Fixed argv, no shell, so the path/principals are never shell-interpreted.
    result = subprocess.run(  # nosec B603 B607
        ["icacls", *args], check=True, capture_output=True, text=capture_text, timeout=10
    )
    return result.stdout if capture_text else ""


def _restrict_to_owner_windows(path: Path) -> bool:
    """Make the ACL on `path` list only the current user. Returns True if it succeeded.

    `/inheritance:r` alone is not enough: it drops *inherited* entries, but a file created
    by an administrator can carry *explicit* SYSTEM/Administrators entries (from the
    process token's default DACL), which survive it. So after granting the user access we
    read the ACL back and remove every other principal explicitly.
    """
    try:
        name, sid = _windows_identity()
        target = str(path)
        _icacls(target, "/inheritance:r", "/grant:r", f"*{sid}:(R,W)")
        for principal in parse_icacls_principals(_icacls(target, capture_text=True), target):
            if principal.lower() != name.lower():
                _icacls(target, "/remove:g", f"*{principal}" if principal.startswith("S-1-") else principal)
    except (OSError, ValueError, StopIteration, subprocess.SubprocessError) as exc:
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
        'icacls "%s" /inheritance:r /grant:r "%%USERNAME%%:(R,W)"',
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
