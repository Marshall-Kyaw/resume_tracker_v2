# Job Application Tracker

A web app — Streamlit + Postgres — for tracking job applications: pipeline
status, resume versions, follow-ups, and interview rounds, with a
dashboard. Supports **Google (Gmail) login**, so each person who uses the
app only ever sees their own data. Built to run on **Streamlit Community
Cloud** so you can use it from your phone.

## Why Postgres instead of the SQLite version

Streamlit Community Cloud's filesystem is ephemeral — any local file
(including a SQLite `.db` file) gets wiped every time the app reboots,
sleeps and wakes up, or you push a code update. For a tracker you actually
rely on, that's data loss waiting to happen. This version stores data in a
free hosted Postgres database (Supabase) instead, so it survives reboots
and redeploys. Everything else about the app is unchanged.

## 1. Install

```bash
pip install -r requirements.txt
```

## 2. Create a free Postgres database (Supabase)

1. Go to <https://supabase.com>, sign up free, create a new project (pick
   any name/region/password — save the password, you'll need it).
2. Once it's ready: **Project Settings → Database → Connection string**.
3. Select the **Session pooler** tab (not "Direct connection" — direct
   connections are IPv6-only now and will fail from Streamlit Community
   Cloud; the session pooler is IPv4-compatible and meant for persistent
   apps like this one).
4. Copy the URI and replace `[YOUR-PASSWORD]` in it with your actual
   database password.

## 3. Set up Google login (one-time)

1. Go to <https://console.cloud.google.com/apis/credentials>, create a
   project (or pick an existing one).
2. If prompted, configure the "OAuth consent screen" first — choose
   **External**, fill in an app name and your email. While the app is in
   "Testing" mode, add your own Gmail (and anyone else who should be able
   to log in) under **Test users** — that's enough for personal/small-group
   use, no need to submit for verification.
3. Back on **Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Web application**
   - Authorized redirect URIs — add:
     - `http://localhost:8501/oauth2callback` (for running locally)
     - `https://YOUR-APP-NAME.streamlit.app/oauth2callback` (add this once
       you know your deployed URL — see step 5)
4. Click **Create**. Copy the **Client ID** and **Client secret**.

## 4. Configure secrets (local)

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` and fill in:
- `[auth] cookie_secret` — any random string, e.g.
  `python -c "import secrets; print(secrets.token_hex(32))"`
- `[auth] redirect_uri` — the localhost one for now
- `[auth.google] client_id` / `client_secret` — from step 3
- `[connections.postgresql] url` — the session pooler URI from step 2

**Never commit `.streamlit/secrets.toml`** — it's already in `.gitignore`.
Only `secrets.toml.example` (with placeholders) should go to GitHub.

## 5. Deploy to Streamlit Community Cloud

1. Push this folder to a GitHub repo (secrets.toml excluded, per
   `.gitignore`).
2. Go to <https://share.streamlit.io>, deploy the repo, pointing at
   `app.py`.
3. Once deployed, note your app's URL (`https://your-app-name.streamlit.app`).
4. Go back to Google Cloud Console and add
   `https://your-app-name.streamlit.app/oauth2callback` as an authorized
   redirect URI (step 3 above).
5. In your Community Cloud app's **Settings → Secrets**, paste the same
   content as your local `secrets.toml`, but change `redirect_uri` to the
   `https://...streamlit.app/oauth2callback` URL.
6. Reboot the app from the Community Cloud dashboard so it picks up the
   new secrets.
7. Open the URL — on desktop or your phone's browser — and log in with
   Google.

## How the per-user data works

- Every application row is stamped with the logged-in user's email
  (`st.user.email`) at creation time.
- Every read/write query filters by that email — one person's login can
  never see or edit another's rows, even though everyone shares the same
  database.
- Follow-ups and interviews inherit their owner through the application
  they belong to, and are protected by an ownership check before any
  write.
- All SQL is parameterized (SQLAlchemy `text()` with named binds) — no
  string-built queries, no injection risk.

This is intentionally "reasonably secure, not maximal": real Google
identity + per-row filtering covers casual/personal use well. If you ever
want to go further, Supabase supports Postgres Row-Level Security (RLS)
policies as a second, database-side enforcement layer — not necessary for
solo or small-group use, but worth knowing it's there.

## Customizing

- `db.STATUS_OPTIONS`, `db.MARKET_OPTIONS`, `db.SOURCE_OPTIONS` in `db.py`
  control the dropdown choices.
- To restrict login to specific people only, keep the Google OAuth
  consent screen in "Testing" mode and only add those Gmail addresses as
  **Test users** — anyone else's Google login is rejected by Google
  before it reaches the app.

## Note on PythonAnywhere

PythonAnywhere does not support Streamlit — its hosting model can't keep
the WebSocket connection Streamlit needs open — so it isn't an option for
this app. Use Streamlit Community Cloud as above.
