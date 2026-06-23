# WhatsApp Visit Tracker

A minimal FastAPI service that records whether a WhatsApp bot user (identified
by their `wa_id` / phone number) has interacted with the bot before.

Persistence is via SQLModel and is chosen entirely by the `DATABASE_URL`
environment variable:

- **Local dev / tests:** defaults to a local SQLite file (`./users.db`) — no
  setup needed.
- **Production:** point `DATABASE_URL` at a Postgres database and it just works
  (the visit upsert is dialect-aware). See "Deploy for free" below.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

The API listens on `http://127.0.0.1:8000`. Interactive docs are at
`http://127.0.0.1:8000/docs`. A `users.db` SQLite file is created on first run.

## Endpoints

| Method | Path             | Description                                  |
| ------ | ---------------- | -------------------------------------------- |
| POST   | `/visits/check`  | Record a visit; reports if the user is new.  |
| GET    | `/users/{phone}` | Fetch a stored user record (404 if missing). |
| GET    | `/health`        | Liveness probe.                              |

### Example: POST /visits/check

```bash
curl -s -X POST http://127.0.0.1:8000/visits/check \
  -H "Content-Type: application/json" \
  -d '{"phone": "+14155550100"}'
```

First call:

```json
{
  "phone": "+14155550100",
  "is_returning": false,
  "first_seen_at": "2026-06-23T12:00:00+00:00",
  "last_seen_at": "2026-06-23T12:00:00+00:00",
  "visit_count": 1
}
```

Call it again with the same phone and `is_returning` becomes `true`,
`visit_count` increments, and `last_seen_at` advances.

The write is performed as a single `INSERT ... ON CONFLICT DO UPDATE`, so two
simultaneous first-hits from the same number cannot double-create the row.

The `phone` field is normalized: whitespace is stripped and a single leading
`+` is preserved. An empty or non-string `phone` yields a `422` response.

## Tests

```bash
pytest
```

## Deploy for free (Render + Neon Postgres)

Both Render and Neon have genuine free tiers that **don't require a credit
card**. Render runs the app; Neon stores the data permanently (Render's own
disk is ephemeral, so we keep state in Neon instead).

### 1. Create a free Postgres database on Neon

1. Sign up at <https://neon.tech> (free, no card).
2. Create a project — a database is created automatically.
3. Copy the **connection string**. It looks like:

   ```
   postgresql://user:password@ep-xxx.region.aws.neon.tech/dbname?sslmode=require
   ```

   The app rewrites the driver prefix automatically, so paste it as-is.

### 2. Push this project to GitHub

Render deploys from a Git repo:

```bash
git init && git add . && git commit -m "WhatsApp visit tracker"
gh repo create whatsapp-visit-tracker --public --source=. --push
# (or create the repo on github.com and `git push` to it)
```

### 3. Deploy on Render

1. Sign up at <https://render.com> (free, no card) and connect your GitHub.
2. **New + → Blueprint**, pick this repo. Render reads `render.yaml` and
   `Dockerfile` automatically. (Or **New + → Web Service**, select the repo,
   and choose the Docker runtime + Free plan manually.)
3. When prompted for the `DATABASE_URL` environment variable, paste the Neon
   connection string from step 1.
4. Click **Deploy**. The app's tables are created automatically on startup.

### 4. Try it

Render gives you a URL like `https://whatsapp-visit-tracker.onrender.com`:

```bash
curl -s -X POST https://<your-app>.onrender.com/visits/check \
  -H "Content-Type: application/json" \
  -d '{"phone": "+14155550100"}'
```

Notes on the free tier:

- Free Render services **sleep after ~15 min of inactivity**; the first request
  after that takes a few seconds to wake (cold start). Visit data is safe — it
  lives in Neon, not on Render's disk.
- Nothing here expires or needs a card. If you later want no cold starts,
  Render's paid Starter plan keeps the service always on.
