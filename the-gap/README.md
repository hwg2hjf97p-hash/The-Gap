# The Gap — MVP Web App

**causalme.com** · Personal Causal Intelligence Layer

Upload your Apple Health or Whoop export and receive verified cause-and-effect
insights about your own health — powered by Microsoft EconML's LinearDML.

---

## Architecture

```
Frontend (Next.js 14)  →  Vercel
Backend  (FastAPI)     →  Railway
Database (Supabase)    →  Supabase free tier
```

### Why Railway for the backend?
Apple Health XML exports can be 50 MB–2 GB. Causal inference runs in 20–60s.
Vercel serverless functions time out at 10s and cap at 4.5 MB — not suitable.
Railway gives us persistent compute with no timeout limit.

---

## Local Development

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env           # fill in values
uvicorn main:app --reload --port 8000
```

API docs at http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
cp ../.env.example .env.local     # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

App at http://localhost:3000

---

## Deployment

### Backend → Railway

1. Push to GitHub
2. Create a new Railway project → "Deploy from GitHub repo"
3. Select the `the-gap/backend` directory as root
4. Set environment variables (copy from `.env.example`)
5. Railway auto-detects the Procfile and starts the server

### Frontend → Vercel

1. Connect the same GitHub repo to Vercel
2. Set root directory to `the-gap/frontend`
3. Set environment variables:
   - `NEXT_PUBLIC_API_URL` = your Railway backend URL
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
4. Deploy — Vercel auto-builds on every push

### Supabase — one-time setup

Run this SQL in your Supabase project's SQL editor:

```sql
CREATE TABLE results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  data_source TEXT NOT NULL,
  data_period_days INTEGER,
  insights JSONB NOT NULL,
  share_url TEXT
);
```

---

## API Reference

### POST /analyse

Upload a health export and receive insights.

**Request:** `multipart/form-data`
- `file`: Apple Health `.xml` / `.zip`, or Whoop `.csv`
- `data_source`: `"apple_health"` or `"whoop"`

**Response:**
```json
{
  "session_id": "uuid",
  "share_url": "https://causalme.com/results/uuid",
  "data_summary": { "days": 123, "source": "apple_health" },
  "insights": [...]
}
```

**Error codes:**
- `422 INSUFFICIENT_DATA` — fewer than 30 days
- `422 PARSE_FAILED` — can't read the file
- `400 UNSUPPORTED_SOURCE` — unknown data_source
- `422 FILE_TOO_LARGE` — over 500 MB
- `500 ENGINE_ERROR` — causal inference crashed

### GET /results/{session_id}

Retrieve previously saved results by session ID.

---

## Contact

hello@causalme.com · Samuel Roberts · Brisbane, QLD, Australia
