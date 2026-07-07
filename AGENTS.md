# historical-data-fetcher

## Setup

```bash
./setup_venv.sh          # Creates venv/, installs package -e ., runs `playwright install chromium`
```

- Python >=3.14 required (`requires-python` in pyproject.toml)
- `.env` at repo root contains Upstox credentials + `DATA_DIR` (gitignored)
- `direnv` users: `.envrc` auto-sources `venv/bin/activate`

## Architecture

- .env file is functional and correctly written 
- Leverage existing functions rather than creating yours
- Ensure separation of concern