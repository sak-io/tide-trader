"""End-to-end smoke test: boot the real backend process and exercise it over HTTP.

Unlike the unit tests this starts `python -m app.main` as a subprocess, so it covers
what the tests can't: the process actually starts, writes its access token, enforces
auth, and (on Windows) leaves that token readable by the current user only.

It is isolated from any real install: a free port, and a throwaway token path and
database in a temp directory *inside the home directory* (so Windows ACL inheritance
behaves as it does for the real `%USERPROFILE%\\.tide-trader`). Cleaned up afterwards.

Usage: uv run python scripts/smoke_test.py
"""

import json
import os
import shutil
import socket
import subprocess  # nosec B404
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run from anywhere: find `app`
from app.security.access_token import parse_icacls_principals  # noqa: E402

STARTUP_TIMEOUT_S = 60


def fail(message: str) -> None:
    print(f"SMOKE FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get(url: str, token: str | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url)  # noqa: S310 - fixed http://127.0.0.1 URL
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310  # nosec B310
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def wait_for_backend(process: subprocess.Popen, url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            fail(f"backend exited early with code {process.returncode}")
        try:
            get(url)
            return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.5)
    fail(f"backend did not accept connections within {STARTUP_TIMEOUT_S}s")


def check_windows_acl(token_path: Path) -> None:
    acl = subprocess.run(  # nosec B603 B607
        ["icacls", str(token_path)], capture_output=True, text=True, check=True, timeout=10
    )
    me = subprocess.run(  # nosec B603 B607
        ["whoami"], capture_output=True, text=True, check=True, timeout=10
    ).stdout.strip()
    print(acl.stdout)
    principals = parse_icacls_principals(acl.stdout, str(token_path))
    if [p.lower() for p in principals] != [me.lower()]:
        fail(f"token ACL should list only {me}, got {principals}")


def main() -> None:
    work_dir = Path(tempfile.mkdtemp(prefix="tide-smoke-", dir=Path.home()))
    token_path = work_dir / "access-token"
    port = free_port()
    status_url = f"http://127.0.0.1:{port}/api/v1/alpaca/status"
    env = {
        **os.environ,
        "PORT": str(port),
        "TIDE_TRADER_ACCESS_TOKEN_PATH": str(token_path),
        "DB_PATH": str(work_dir / "state.db"),
    }
    process = subprocess.Popen([sys.executable, "-m", "app.main"], env=env)  # nosec B603
    try:
        wait_for_backend(process, status_url)

        if not token_path.exists():
            fail(f"access token was not created at {token_path}")
        token = token_path.read_text(encoding="utf-8").strip()
        if not token:
            fail("access token file is empty")

        status, _ = get(status_url)
        if status != 401:
            fail(f"unauthenticated request should be 401, got {status}")

        status, _ = get(status_url, "wrong-token")
        if status != 401:
            fail(f"wrong token should be 401, got {status}")

        status, body = get(status_url, token)
        if status != 200:
            fail(f"authenticated request should be 200, got {status}: {body}")
        print("alpaca status:", json.loads(body))

        if sys.platform == "win32":
            check_windows_acl(token_path)
        else:
            mode = token_path.stat().st_mode & 0o777
            if mode != 0o600:
                fail(f"token mode should be 0o600, got {oct(mode)}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            fail("backend did not shut down within 15s of terminate()")
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    print("SMOKE OK")


if __name__ == "__main__":
    main()
