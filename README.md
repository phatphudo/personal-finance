# 💰 Personal Finance Dashboard

A personal finance tracking app built with [Streamlit](https://streamlit.io/), backed by **Google Sheets** as the data source. Track work hours, budget, and cash flow — all from a clean, dark-mode dashboard.

---

## Features

- ⏱️ **Work Hours** — current pay period & period comparison
- 💳 **Budget Tracker** — current month & monthly comparison
- ⚙️ **Settings** — manage categories and spreadsheet config
- 🔄 Live data refresh from Google Sheets

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.12+ |
| [uv](https://docs.astral.sh/uv/) | latest |
| [make](https://www.gnu.org/software/make/) | any (pre-installed on macOS) |
| Docker | 24+ (for containerised deploy) |
| Google Cloud service account JSON | — |

---

## Secrets Setup

The app requires two secret files. **These are never committed to git.**

### 1. `.streamlit/secrets.toml`

```toml
# .streamlit/secrets.toml
[sheets]
spreadsheet_id = "<your-google-spreadsheet-id>"
```

### 2. `.secret/<service-account>.json`

Place your Google Cloud service account key (JSON) inside the `.secret/` directory.
The filename can be anything — the app picks it up automatically.

---

## Running Locally (without Docker)

```bash
# Install dependencies
uv sync

# Start the app
make dev
# or directly:
uv run streamlit run main.py
```

The dashboard will be available at **http://localhost:8501**.

---

## Running with Docker

> **First build** installs all dependencies (~60 s). Subsequent builds that only
> change source code (not `pyproject.toml` / `uv.lock`) complete in **seconds**
> thanks to layer caching.
>
> Secrets live **outside** the image and are bind-mounted at runtime — they are
> never baked into the image.

```bash
make build   # build the image
make run     # start the container → http://localhost:8501
make logs    # tail logs
make stop    # stop & remove the container
make restart # stop then start in one step
```

See [Make Commands](#make-commands) below for the full reference.

### Docker Compose (optional)

Save the snippet below as `docker-compose.yml` for a one-command workflow:

```yaml
services:
  app:
    build: .
    image: personal-finance
    ports:
      - "8501:8501"
    volumes:
      - ./.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro
      - ./.secret:/app/.secret:ro
    restart: unless-stopped
```

```bash
docker compose up -d          # start
docker compose logs -f        # tail logs
docker compose down           # stop
```

---

## Make Commands

Run `make help` (or just `make`) to see all available targets.

| Command | Description |
|---------|-------------|
| `make dev` | Run the app locally with `uv` |
| `make build` | Build the Docker image |
| `make build-no-cache` | Rebuild from scratch (ignores layer cache) |
| `make run` | Start the container, mount secrets, expose port 8501 |
| `make stop` | Stop and remove the container |
| `make restart` | `stop` + `run` in one command (no rebuild) |
| `make redeploy` | `stop` → `build` → `prune` → `run` — full rebuild cycle |
| `make prune` | Remove dangling (untagged) Docker images |
| `make logs` | Tail container logs (`Ctrl-C` to exit) |
| `make shell` | Open a bash shell inside the running container |
| `make clean` | Remove the Docker image |

> **Typical workflow after code changes:**
> ```bash
> make redeploy   # rebuilds image, cleans old layers, starts a fresh container
> ```

You can override defaults at call-time:

```bash
make run PORT=9000          # expose on a different host port
make build IMAGE=my-tag     # tag the image differently
```

---

## Project Structure

```
personal-finance/
├── main.py                  # Streamlit entry point & global layout
├── components/
│   ├── budget/              # Budget tracker views
│   └── work_hours/          # Work hours views
├── gsheets/                 # Google Sheets read/write helpers
├── utils/                   # Shared utilities
├── .streamlit/
│   ├── config.toml          # Streamlit server config (committed)
│   └── secrets.toml         # ⚠️ NOT committed — add manually
├── .secret/                 # ⚠️ NOT committed — add service account JSON
├── Dockerfile
├── .dockerignore
├── Makefile
├── pyproject.toml
└── uv.lock
```

---

## How the Docker Image is Optimised

| Technique | Benefit |
|-----------|---------|
| **Multi-stage build** | Builder stage (~700 MB) discarded; runtime image is slim-bookworm (~200 MB) |
| **uv cache mount** (`--mount=type=cache`) | Pip wheel cache persists across builds on the same host |
| **Deps copied before source** | `uv sync` layer is only invalidated when `pyproject.toml` / `uv.lock` change |
| **`fileWatcherType=none`** | Disables inotify file watcher — unnecessary overhead in containers |
| **`.dockerignore`** | Excludes `.venv`, `__pycache__`, secrets, and git history from the build context |
