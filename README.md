# monte-carlo-jaab-api

Azraq Monte Carlo risk engine — single FastAPI app (`azraq_mc`).

**Plain-language overview** (what it is, what’s built, how data sources fit in): **[docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)**.

**Integration (one project, auth, reset, mapping checklist):** **[docs/INTEGRATION.md](docs/INTEGRATION.md)**.

**All endpoints (parameters, bodies, responses, usage):** **[docs/ENDPOINTS.md](docs/ENDPOINTS.md)** (includes a **numbered inventory of all 21** routes + `/docs` / `/openapi.json` / `/app`). Alternate layout: **[docs/API_ENDPOINTS_REFERENCE.md](docs/API_ENDPOINTS_REFERENCE.md)**.

**PDF export (same content, print-ready):** **[docs/Azraq_Monte_Carlo_API_Reference.pdf](docs/Azraq_Monte_Carlo_API_Reference.pdf)** — regenerate with `python scripts/build_api_reference_pdf.py` (needs **Markdown** + **Edge** or **Chrome** headless; see script docstring).

## Run

From the repo root:

```bash
pip install -r requirements.txt
python -m uvicorn azraq_mc.api:app --reload --host 127.0.0.1 --port 8000
```

- Interactive API: `http://127.0.0.1:8000/docs`
- **Scenario lab (static UI):** `http://127.0.0.1:8000/app/` (single-asset) · `http://127.0.0.1:8000/app/portfolio/` (portfolio v2)
- Reference: `docs/API.md` · `docs/ENDPOINTS.md` · `docs/INTEGRATION.md`

Optional: set `AZRAQ_API_KEY` in `.env`; send `X-API-Key` on routes that require it (`GET /health` is public).
