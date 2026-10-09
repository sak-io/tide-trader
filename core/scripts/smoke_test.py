"""End-to-end smoke test: boot the real backend process and exercise it over HTTP.

Unlike the unit tests this starts `python -m app.main` as a subprocess against the
real default token location, so it covers what the tests can't: the process actually
starts, writes its access token where the Electron app looks for it, enforces auth,
and (on Windows) leaves that token readable by the current user only.

Usage: uv run python scripts/smoke_test.py
"""

import getpass
import json
import subprocess  # nosec B404
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"
STATUS_URL = f"{BASE_URL}/api/v1/alpaca/status"
TOKEN_PATH = Path.home() / ".tide-trader" / "access-token"
STARTUP_TIMEOUT_S = 60

# Principals that must NOT appear in the token's ACL on Windows.
FORBIDDEN_PRINCIPALS = ("Everyone", "BUILTIN\\Users", "Authenticated Users", "Administrators", "SYSTEM")


def fail(message: str) -> None:
    print(f"SMOKE FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def get(url: str, token: str | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url)  # noqa: S310 - fixed http://127.0.0.1 URL
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310  # nosec B310
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def wait_for_backend(process: subprocess.Popen) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            fail(f"backend exited early with code {process.returncode}")
        try:
            get(STATUS_URL)
            return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.5)
    fail(f"backend did not accept connections within {STARTUP_TIMEOUT_S}s")


def check_windows_acl() -> None:
    # TEMP DIAGNOSTIC: does running the same icacls command by hand harden the file?
    manual = subprocess.run(  # nosec B603 B607
        ["icacls", str(TOKEN_PATH), "/inheritance:r", "/grant:r", f"{getpass.getuser()}:F"],
        capture_output=True, text=True, timeout=10,
    )
    print("MANUAL icacls rc=", manual.returncode, manual.stdout, manual.stderr)
    result = subprocess.run(  # nosec B603 B607
        ["icacls", str(TOKEN_PATH)], capture_output=True, text=True, check=True, timeout=10
    )
    print(result.stdout)
    # icacls prints "<path> <principal>:(F)" then one indented line per further entry.
    entries = [line for line in result.stdout.splitlines() if ":(" in line]
    if not entries:
        fail("could not parse any ACL entries from icacls output")
    for entry in entries:
        for principal in FORBIDDEN_PRINCIPALS:
            if principal.lower() in entry.lower():
                fail(f"token ACL grants access to {principal}: {entry.strip()}")
    if not any(getpass.getuser().lower() in entry.lower() for entry in entries):
        fail("token ACL does not grant the current user access")


def main() -> None:
    process = subprocess.Popen([sys.executable, "-m", "app.main"])  # nosec B603
    try:
        wait_for_backend(process)

        if not TOKEN_PATH.exists():
            fail(f"access token was not created at {TOKEN_PATH}")
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()

        status, _ = get(STATUS_URL)
        if status != 401:
            fail(f"unauthenticated request should be 401, got {status}")

        status, body = get(STATUS_URL, "wrong-token")
        if status != 401:
            fail(f"wrong token should be 401, got {status}")

        status, body = get(STATUS_URL, token)
        if status != 200:
            fail(f"authenticated request should be 200, got {status}: {body}")
        print("alpaca status:", json.loads(body))

        if sys.platform == "win32":
            check_windows_acl()
        else:
            mode = TOKEN_PATH.stat().st_mode & 0o777
            if mode != 0o600:
                fail(f"token mode should be 0o600, got {oct(mode)}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            fail("backend did not shut down within 15s of terminate()")

    print("SMOKE OK")


if __name__ == "__main__":
    main()
