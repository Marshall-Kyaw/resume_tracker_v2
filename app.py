"""
Job Application Tracker — Streamlit + SQLite

Run with:  streamlit run app.py
"""
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import db

st.set_page_config(page_title="Job Application Tracker", page_icon="\U0001F4BC", layout="wide")

db.init_db()

# ---------------------------------------------------------------- Login gate
if not st.user.is_logged_in:
    st.title("\U0001F4BC Job Application Tracker")
    st.write("Sign in with Google to see and manage your own applications.")
    st.button("Log in with Google", on_click=st.login, args=["google"])
    st.stop()

user_email = st.user.email

st.sidebar.caption(f"Signed in as {user_email}")
st.sidebar.button("Log out", on_click=st.logout)


PAGES = ["Dashboard", "Applications", "Add Application", "Follow-ups", "Interviews"]

st.sidebar.title("\U0001F4BC Job Tracker")
page = st.sidebar.radio("Go to", PAGES, label_visibility="collapsed")


def as_df(rows):
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ---------------------------------------------------------------- Dashboard
if page == "Dashboard":
    st.title("Dashboard")
    apps = db.get_all_applications(user_email)
    df = as_df(apps)

    if df.empty:
        st.info("No applications yet. Add your first one from the **Add Application** page.")
    else:
        total = len(df)
        active = df[df["status"].isin(db.ACTIVE_STATUSES)].shape[0]
        interviewing = df[df["status"] == "Interviewing"].shape[0]
        offers = df[df["status"] == "Offer"].shape[0]
        responded = df[~df["status"].isin(["Saved", "Applying", "Applied"])].shape[0]
        response_rate = (responded / total * 100) if total else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total applications", total)
        c2.metric("Active", active)
        c3.metric("Interviewing", interviewing)
        c4.metric("Offers", offers)
        c5.metric("Response rate", f"{response_rate:.0f}%")

        st.divider()
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Status breakdown")
            status_counts = df["status"].value_counts().reset_index()
            status_counts.columns = ["status", "count"]
            fig = px.bar(status_counts, x="status", y="count", color="status")
            fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Applications by market")
            market_counts = df["target_market"].fillna("Unspecified").value_counts().reset_index()
            market_counts.columns = ["market", "count"]
            fig2 = px.pie(market_counts, names="market", values="count", hole=0.4)
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Applications over time")
        timed = df.dropna(subset=["date_applied"]).copy()
        if not timed.empty:
            timed["date_applied"] = pd.to_datetime(timed["date_applied"], errors="coerce")
            timed = timed.dropna(subset=["date_applied"])
            weekly = timed.set_index("date_applied").resample("W").size().reset_index(name="count")
            fig3 = px.line(weekly, x="date_applied", y="count", markers=True)
            fig3.update_layout(xaxis_title=None, yaxis_title="Applications")
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.caption("No dated applications yet.")

        st.subheader("\u26A0\uFE0F Stale applications (active, no update in 14+ days)")
        timed_all = df.copy()
        timed_all["updated_at"] = pd.to_datetime(timed_all["updated_at"], errors="coerce")
        cutoff = datetime.now() - timedelta(days=14)
        stale = timed_all[
            timed_all["status"].isin(db.ACTIVE_STATUSES) & (timed_all["updated_at"] < cutoff)
        ]
        if stale.empty:
            st.caption("Nothing stale \u2014 good.")
        else:
            st.dataframe(
                stale[["company", "role_title", "status", "updated_at"]],
                use_container_width=True, hide_index=True
            )

# ---------------------------------------------------------------- Applications
elif page == "Applications":
    st.title("Applications")
    apps = db.get_all_applications(user_email)
    df = as_df(apps)

    if df.empty:
        st.info("No applications yet.")
    else:
        col1, col2, col3 = st.columns(3)
        status_filter = col1.multiselect("Status", db.STATUS_OPTIONS)
        market_filter = col2.multiselect("Market", db.MARKET_OPTIONS)
        search = col3.text_input("Search company / role")

        filtered = df.copy()
        if status_filter:
            filtered = filtered[filtered["status"].isin(status_filter)]
        if market_filter:
            filtered = filtered[filtered["target_market"].isin(market_filter)]
        if search:
            mask = (
                filtered["company"].str.contains(search, case=False, na=False)
                | filtered["role_title"].str.contains(search, case=False, na=False)
            )
            filtered = filtered[mask]

        st.dataframe(
            filtered[["id", "company", "role_title", "target_market", "status",
                      "date_applied", "resume_version", "source"]],
            use_container_width=True, hide_index=True
        )

        st.download_button(
            "Export filtered view to CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            "job_applications.csv", "text/csv"
        )

        st.divider()
        st.subheader("Edit / delete an application")
        app_ids = filtered["id"].tolist()
        if app_ids:
            selected_id = st.selectbox(
                "Select by ID", app_ids,
                format_func=lambda i: f"{i} — {df.loc[df['id'] == i, 'company'].values[0]} "
                                       f"({df.loc[df['id'] == i, 'role_title'].values[0]})"
            )
            record = db.get_application(user_email, selected_id)

            with st.form("edit_form"):
                c1, c2 = st.columns(2)
                company = c1.text_input("Company", record["company"])
                role_title = c2.text_input("Role", record["role_title"])

                c3, c4, c5 = st.columns(3)
                market = c3.selectbox("Market", db.MARKET_OPTIONS,
                                       index=db.MARKET_OPTIONS.index(record["target_market"])
                                       if record["target_market"] in db.MARKET_OPTIONS else 0)
                status = c4.selectbox("Status", db.STATUS_OPTIONS,
                                       index=db.STATUS_OPTIONS.index(record["status"])
                                       if record["status"] in db.STATUS_OPTIONS else 0)
                source = c5.selectbox("Source", db.SOURCE_OPTIONS,
                                       index=db.SOURCE_OPTIONS.index(record["source"])
                                       if record["source"] in db.SOURCE_OPTIONS else 0)

                c6, c7 = st.columns(2)
                date_applied = c6.text_input("Date applied (YYYY-MM-DD)", record["date_applied"] or "")
                resume_version = c7.text_input("Resume version", record["resume_version"] or "")

                job_url = st.text_input("Job URL", record["job_url"] or "")
                referral_contact = st.text_input("Referral contact", record["referral_contact"] or "")
                salary_range = st.text_input("Salary range", record["salary_range"] or "")
                notes = st.text_area("Notes", record["notes"] or "")

                save_col, delete_col = st.columns(2)
                submitted = save_col.form_submit_button("Save changes", use_container_width=True)
                deleted = delete_col.form_submit_button("Delete application", use_container_width=True)

                if submitted:
                    db.update_application(user_email, selected_id, {
                        "company": company, "role_title": role_title, "target_market": market,
                        "status": status, "date_applied": date_applied,
                        "resume_version": resume_version, "source": source, "job_url": job_url,
                        "referral_contact": referral_contact, "salary_range": salary_range,
                        "notes": notes
                    })
                    st.success("Saved.")
                    st.rerun()

                if deleted:
                    db.delete_application(user_email, selected_id)
                    st.success("Deleted.")
                    st.rerun()

# ---------------------------------------------------------------- Add Application
elif page == "Add Application":
    st.title("Add Application")
    with st.form("add_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        company = c1.text_input("Company *")
        role_title = c2.text_input("Role *")

        c3, c4, c5 = st.columns(3)
        market = c3.selectbox("Target market", db.MARKET_OPTIONS)
        status = c4.selectbox("Status", db.STATUS_OPTIONS)
        source = c5.selectbox("Source", db.SOURCE_OPTIONS)

        c6, c7 = st.columns(2)
        date_applied = c6.date_input("Date applied", value=date.today())
        resume_version = c7.text_input("Resume version (e.g. 'network-security-v2')")

        job_url = st.text_input("Job URL")
        referral_contact = st.text_input("Referral contact (if any)")
        salary_range = st.text_input("Salary range")
        notes = st.text_area("Notes")

        submitted = st.form_submit_button("Add application", use_container_width=True)
        if submitted:
            if not company or not role_title:
                st.error("Company and Role are required.")
            else:
                new_id = db.add_application(user_email, {
                    "company": company, "role_title": role_title, "target_market": market,
                    "status": status, "date_applied": str(date_applied),
                    "resume_version": resume_version, "source": source, "job_url": job_url,
                    "referral_contact": referral_contact, "salary_range": salary_range,
                    "notes": notes
                })
                st.success(f"Added '{company} — {role_title}' (id {new_id}).")

# ---------------------------------------------------------------- Follow-ups
elif page == "Follow-ups":
    st.title("Follow-ups")
    apps = db.get_all_applications(user_email)

    st.subheader("Add a follow-up")
    if apps:
        with st.form("followup_form", clear_on_submit=True):
            app_choice = st.selectbox(
                "Application", apps,
                format_func=lambda a: f"{a['company']} — {a['role_title']}"
            )
            follow_date = st.date_input("Follow-up date", value=date.today() + timedelta(days=7))
            description = st.text_input("What needs to happen (e.g. 'Email recruiter for update')")
            submitted = st.form_submit_button("Add follow-up")
            if submitted:
                db.add_follow_up(user_email, app_choice["id"], str(follow_date), description)
                st.success("Follow-up added.")
                st.rerun()
    else:
        st.info("Add an application first.")

    st.divider()
    st.subheader("Upcoming / overdue")
    follow_ups = db.get_follow_ups(user_email, include_completed=False)
    if not follow_ups:
        st.caption("Nothing pending.")
    else:
        today_str = str(date.today())
        for f in follow_ups:
            overdue = f["follow_up_date"] and f["follow_up_date"] < today_str
            marker = "\U0001F534" if overdue else "\U0001F7E2"
            label = f"{marker} {f['follow_up_date']} — " \
                    f"{f['company']} ({f['role_title']}): {f['description']}"
            col1, col2 = st.columns([5, 1])
            col1.write(label)
            if col2.button("Done", key=f"done_{f['id']}"):
                db.complete_follow_up(user_email, f["id"])
                st.rerun()

# ---------------------------------------------------------------- Interviews
elif page == "Interviews":
    st.title("Interviews")
    apps = db.get_all_applications(user_email)

    st.subheader("Log an interview round")
    if apps:
        with st.form("interview_form", clear_on_submit=True):
            app_choice = st.selectbox(
                "Application", apps,
                format_func=lambda a: f"{a['company']} — {a['role_title']}"
            )
            round_type = st.text_input("Round (e.g. 'HR screen', 'Technical', 'Final')")
            interview_date = st.date_input("Date", value=date.today())
            outcome = st.selectbox("Outcome", ["Pending", "Passed", "Failed", "Withdrawn"])
            notes = st.text_area("Notes (questions asked, impressions, follow-up needed)")
            submitted = st.form_submit_button("Add interview")
            if submitted:
                db.add_interview(user_email, app_choice["id"], round_type, str(interview_date), notes, outcome)
                st.success("Interview logged.")
                st.rerun()
    else:
        st.info("Add an application first.")

    st.divider()
    st.subheader("Interview history")
    interviews = db.get_interviews(user_email)
    if not interviews:
        st.caption("No interviews logged yet.")
    else:
        idf = as_df(interviews)
        st.dataframe(
            idf[["interview_date", "company", "role_title", "round_type", "outcome", "notes"]],
            use_container_width=True, hide_index=True
        )
