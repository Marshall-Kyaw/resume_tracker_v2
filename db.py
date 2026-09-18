"""
Database layer for the Job Application Tracker.

Backed by a hosted Postgres database (e.g. Supabase's free tier) via
Streamlit's built-in SQL connection (`st.connection`). Local SQLite is
intentionally NOT used here: Streamlit Community Cloud's filesystem is
ephemeral, so a local .db file gets wiped on every reboot/redeploy.

All data is scoped per-user by `user_email` (from Google login, via
st.user.email in app.py) so each person only ever sees their own
applications, follow-ups, and interviews. Every query is parameterized
(SQLAlchemy `text()` with named binds) — no string-built SQL, no
injection risk.
"""
from datetime import datetime

import streamlit as st
from sqlalchemy import text

STATUS_OPTIONS = [
    "Saved", "Applying", "Applied", "In Process",
    "Interviewing", "Offer", "Rejected", "Closed / No Response"
]

MARKET_OPTIONS = ["Malaysia", "Singapore", "UAE", "Japan", "Thailand", "Other"]

SOURCE_OPTIONS = ["LinkedIn", "Company Website", "Referral", "Recruiter", "Job Board", "Other"]

# Statuses considered "active" for stale-application flagging
ACTIVE_STATUSES = {"Applying", "Applied", "In Process", "Interviewing"}


def _conn():
    # Reads connection details from st.secrets["connections"]["postgresql"].
    # Streamlit caches this connection automatically across reruns.
    return st.connection("postgresql", type="sql")


def init_db():
    conn = _conn()
    with conn.session as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS applications (
                id SERIAL PRIMARY KEY,
                user_email TEXT NOT NULL,
                company TEXT NOT NULL,
                role_title TEXT NOT NULL,
                target_market TEXT,
                status TEXT DEFAULT 'Saved',
                date_applied TEXT,
                resume_version TEXT,
                source TEXT,
                job_url TEXT,
                referral_contact TEXT,
                salary_range TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """))
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS follow_ups (
                id SERIAL PRIMARY KEY,
                application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                follow_up_date TEXT,
                description TEXT,
                completed INTEGER DEFAULT 0
            )
        """))
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS interviews (
                id SERIAL PRIMARY KEY,
                application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                round_type TEXT,
                interview_date TEXT,
                notes TEXT,
                outcome TEXT
            )
        """))
        s.commit()


# ---------- Applications ----------

def add_application(user_email: str, data: dict) -> int:
    conn = _conn()
    now = datetime.now().isoformat()
    with conn.session as s:
        result = s.execute(text("""
            INSERT INTO applications
            (user_email, company, role_title, target_market, status, date_applied,
             resume_version, source, job_url, referral_contact, salary_range, notes,
             created_at, updated_at)
            VALUES (:user_email, :company, :role_title, :target_market, :status, :date_applied,
                    :resume_version, :source, :job_url, :referral_contact, :salary_range, :notes,
                    :created_at, :updated_at)
            RETURNING id
        """), dict(
            user_email=user_email, company=data.get("company"), role_title=data.get("role_title"),
            target_market=data.get("target_market"), status=data.get("status", "Saved"),
            date_applied=data.get("date_applied"), resume_version=data.get("resume_version"),
            source=data.get("source"), job_url=data.get("job_url"),
            referral_contact=data.get("referral_contact"), salary_range=data.get("salary_range"),
            notes=data.get("notes"), created_at=now, updated_at=now
        ))
        new_id = result.scalar()
        s.commit()
        return new_id


def update_application(user_email: str, app_id: int, data: dict):
    conn = _conn()
    now = datetime.now().isoformat()
    fields = []
    params = {"app_id": app_id, "user_email": user_email, "updated_at": now}
    for key in ["company", "role_title", "target_market", "status", "date_applied",
                "resume_version", "source", "job_url", "referral_contact",
                "salary_range", "notes"]:
        if key in data:
            fields.append(f"{key} = :{key}")
            params[key] = data[key]
    fields.append("updated_at = :updated_at")
    with conn.session as s:
        s.execute(text(f"""
            UPDATE applications SET {', '.join(fields)}
            WHERE id = :app_id AND user_email = :user_email
        """), params)
        s.commit()


def delete_application(user_email: str, app_id: int):
    conn = _conn()
    with conn.session as s:
        owned = s.execute(text(
            "SELECT id FROM applications WHERE id = :app_id AND user_email = :user_email"
        ), dict(app_id=app_id, user_email=user_email)).fetchone()
        if not owned:
            return
        # Explicit child deletes (belt-and-braces alongside the ON DELETE CASCADE above).
        s.execute(text("DELETE FROM follow_ups WHERE application_id = :app_id"), dict(app_id=app_id))
        s.execute(text("DELETE FROM interviews WHERE application_id = :app_id"), dict(app_id=app_id))
        s.execute(text("DELETE FROM applications WHERE id = :app_id"), dict(app_id=app_id))
        s.commit()


def get_all_applications(user_email: str):
    conn = _conn()
    df = conn.query(
        "SELECT * FROM applications WHERE user_email = :user_email ORDER BY date_applied DESC",
        params={"user_email": user_email}, ttl=0
    )
    return df.to_dict(orient="records")


def get_application(user_email: str, app_id: int):
    conn = _conn()
    df = conn.query(
        "SELECT * FROM applications WHERE id = :app_id AND user_email = :user_email",
        params={"app_id": app_id, "user_email": user_email}, ttl=0
    )
    if df.empty:
        return None
    return df.to_dict(orient="records")[0]


# ---------- Follow-ups ----------
# Scoped via a JOIN back to applications.user_email, so a follow-up can never
# be read or modified through another user's session.

def add_follow_up(user_email: str, application_id: int, follow_up_date: str, description: str):
    conn = _conn()
    with conn.session as s:
        owned = s.execute(text(
            "SELECT id FROM applications WHERE id = :aid AND user_email = :ue"
        ), dict(aid=application_id, ue=user_email)).fetchone()
        if not owned:
            return
        s.execute(text("""
            INSERT INTO follow_ups (application_id, follow_up_date, description, completed)
            VALUES (:aid, :fd, :descr, 0)
        """), dict(aid=application_id, fd=follow_up_date, descr=description))
        s.commit()


def get_follow_ups(user_email: str, include_completed=False):
    conn = _conn()
    query = """
        SELECT f.*, a.company, a.role_title
        FROM follow_ups f JOIN applications a ON f.application_id = a.id
        WHERE a.user_email = :user_email
    """
    if not include_completed:
        query += " AND f.completed = 0"
    query += " ORDER BY f.follow_up_date ASC"
    df = conn.query(query, params={"user_email": user_email}, ttl=0)
    return df.to_dict(orient="records")


def complete_follow_up(user_email: str, follow_up_id: int):
    conn = _conn()
    with conn.session as s:
        s.execute(text("""
            UPDATE follow_ups SET completed = 1
            WHERE id = :fid AND application_id IN (
                SELECT id FROM applications WHERE user_email = :ue
            )
        """), dict(fid=follow_up_id, ue=user_email))
        s.commit()


def delete_follow_up(user_email: str, follow_up_id: int):
    conn = _conn()
    with conn.session as s:
        s.execute(text("""
            DELETE FROM follow_ups
            WHERE id = :fid AND application_id IN (
                SELECT id FROM applications WHERE user_email = :ue
            )
        """), dict(fid=follow_up_id, ue=user_email))
        s.commit()


# ---------- Interviews ----------

def add_interview(user_email: str, application_id: int, round_type: str, interview_date: str,
                   notes: str, outcome: str):
    conn = _conn()
    with conn.session as s:
        owned = s.execute(text(
            "SELECT id FROM applications WHERE id = :aid AND user_email = :ue"
        ), dict(aid=application_id, ue=user_email)).fetchone()
        if not owned:
            return
        s.execute(text("""
            INSERT INTO interviews (application_id, round_type, interview_date, notes, outcome)
            VALUES (:aid, :rt, :idate, :notes, :outcome)
        """), dict(aid=application_id, rt=round_type, idate=interview_date, notes=notes, outcome=outcome))
        s.commit()


def get_interviews(user_email: str, application_id=None):
    conn = _conn()
    if application_id:
        df = conn.query("""
            SELECT i.* FROM interviews i
            JOIN applications a ON i.application_id = a.id
            WHERE i.application_id = :aid AND a.user_email = :ue
            ORDER BY i.interview_date DESC
        """, params={"aid": application_id, "ue": user_email}, ttl=0)
    else:
        df = conn.query("""
            SELECT i.*, a.company, a.role_title
            FROM interviews i JOIN applications a ON i.application_id = a.id
            WHERE a.user_email = :ue
            ORDER BY i.interview_date DESC
        """, params={"ue": user_email}, ttl=0)
    return df.to_dict(orient="records")


def delete_interview(user_email: str, interview_id: int):
    conn = _conn()
    with conn.session as s:
        s.execute(text("""
            DELETE FROM interviews
            WHERE id = :iid AND application_id IN (
                SELECT id FROM applications WHERE user_email = :ue
            )
        """), dict(iid=interview_id, ue=user_email))
        s.commit()
