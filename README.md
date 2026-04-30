# Local SEO Dashboard (Team Edition)

A lightweight local SEO dashboard for small teams. Enter any website URL and receive:
- Technical SEO checks
- SEO score
- Opportunities + fixes
- Keyword opportunities
- Saved report history

## Run

```bash
python3 server.py
```

Open: `http://localhost:3000`

## Environment variables
- `PORT` (default `3000`)
- `SEO_DB_PATH` (default `seo_reports.db`)
- `OPENAI_API_KEY` (optional placeholder for extended AI workflows)

## API
- `POST /api/scan` with JSON `{ "url": "https://example.com" }`
- `GET /api/reports` to retrieve last 20 reports
