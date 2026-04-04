# monte-carlo-jaab-api

Azraq Monte Carlo risk engine — single FastAPI app (`azraq_mc`).

**Plain-language overview** (what it is, what’s built, how data sources fit in): **[docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)**.

## Run

From the repo root:

```bash
pip install -r requirements.txt
python -m uvicorn azraq_mc.api:app --reload --host 127.0.0.1 --port 8000
```

- Interactive API: `http://127.0.0.1:8000/docs`
- Reference: `docs/API.md`

Optional: set `AZRAQ_API_KEY` in `.env`; send `X-API-Key` on routes that require it (`GET /health` is public).
