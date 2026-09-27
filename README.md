# Tide Trader

A macOS desktop app for realtime market research on top of Alpaca's paper trading
API — live quotes, most-active/mover screeners, and historical price charts —
paired with a Python backend that owns order execution and risk controls.

This is an early-stage personal project. The long-term goal is an agent that
proposes trades for a human to approve; today it's a research dashboard plus a
safety-first execution backend, with no autonomous trading yet.

## What's here today

- **Market dashboard** (Electron + React): browse Alpaca's Most Active / Top
  Gainers / Top Losers screeners, search any symbol, and view its live price
  alongside a historical chart (1D/1W/1M/3M/1Y) with a hover tooltip showing
  full OHLCV.
- **Realtime data**: trades, quotes, and minute bars stream in directly from
  Alpaca's IEX feed the moment you select a symbol.
- **A Python backend** (`core/`) that wraps Alpaca's trading + market-data APIs
  behind a small FastAPI service: order placement, account/positions, a
  kill-switch and daily-loss-limit risk manager backed by SQLite (so it
  survives restarts), and the screener/historical-bars endpoints the dashboard
  uses. The order/risk endpoints exist and are fully tested, but the desktop
  UI doesn't call them yet — there is no manual "place a trade" button today.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the pieces fit
together and why they're built this way.

## Prerequisites

- **Node.js 20 or 22** (managed via [nvm](https://github.com/nvm-sh/nvm)
  recommended). Node 26 has a known incompatibility on older macOS versions
  (missing `libc++` symbol) — if `node --version` crashes with a `dyld` error,
  run `nvm install 22 && nvm use 22`.
- **Python 3.12** and [`uv`](https://docs.astral.sh/uv/) for the backend.
- An **Alpaca Paper Trading account** (free) — see below.
- macOS (the Electron app targets macOS; an iOS companion app is a future
  goal, not built yet).

### Getting Alpaca paper trading API keys

1. Sign up at [alpaca.markets](https://alpaca.markets) (or log in).
2. Switch to **Paper Trading** mode (paper accounts are created automatically,
   no approval needed).
3. Go to your Paper Trading dashboard → **API Keys** → **Generate New Key**.
4. Copy both the **API Key ID** and **Secret Key** immediately — the secret is
   only shown once.

## Getting started

### 1. Backend (`core/`)

```bash
cd core
uv sync
cp .env.example .env   # then edit .env and paste in your own API key/secret
uv run python -m app.main
```

The API listens on `http://127.0.0.1:8000` by default. It's intentionally
bound to localhost only — this service can place real (paper) orders and
isn't meant to be reachable from anything but the desktop app on the same
machine.

Run the backend's test suite:

```bash
cd core
uv run pytest                                    # tests
uv run pytest --cov=app --cov-report=term-missing  # with coverage
```

### 2. Desktop app

With the backend running (the dashboard's screener/chart data depends on it):

```bash
npm install
npm run dev
```

On first launch you'll be asked for your Alpaca Paper API Key ID and Secret.
They're validated against Alpaca before being saved, then stored **encrypted**
via Electron's `safeStorage` (backed by the macOS Keychain) — never as a
plaintext file, and never committed to this repo.

### Other useful commands

```bash
npm run typecheck   # TypeScript, both main and renderer
npm run build       # production build (electron-vite)
```

## Running the backend in Docker

The backend (not the desktop app — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#why-not-docker-for-the-desktop-app)
for why) can run in a container, useful for running it on a home server or a
machine other than the one you're clicking around on:

```bash
cd core
cp .env.example .env   # fill in your own keys
docker compose up --build
```

The compose file publishes the API only to `127.0.0.1` on the host (not your
LAN) and persists the risk-manager's SQLite state in a named volume so it
survives container restarts.

## Project structure

```
tide-trader/
├── src/                    # Electron app
│   ├── main/               #   Node process: Alpaca REST/WS client, IPC, credential storage
│   ├── preload/            #   contextBridge API exposed to the renderer
│   ├── renderer/            #   React UI (dashboard, chart, search)
│   └── shared/              #   Types shared between main and renderer
├── core/                   # Python backend
│   ├── app/
│   │   ├── adapters/        #   Alpaca trading / market-data / streaming wrappers
│   │   ├── engine/          #   Risk manager + SQLite-backed state store
│   │   ├── routers/         #   FastAPI routes (orders, account, market, stream)
│   │   └── main.py          #   App assembly + lifespan wiring
│   └── tests/               #   pytest suite (100% line coverage)
└── docs/
    └── ARCHITECTURE.md
```

## Roadmap

- Wire the desktop app to the backend's order/risk-manager endpoints for
  manual trade placement (currently research-only).
- An agent that proposes trades from market data, with a human approving
  before anything executes.
- An iPhone companion app.

## Security notes

- API keys are never written into this repository. `core/.env` and the
  Electron app's local credential store are both gitignored / outside the
  repo entirely.
- The paper trading account this connects to cannot place live orders or move
  real money.
