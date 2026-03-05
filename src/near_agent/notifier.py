"""Email notifier — sends alerts via Resend on bid awards, work completion, and errors."""
from __future__ import annotations

import httpx


RESEND_API_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, body: str, api_key: str, from_addr: str = "NEAR Agent <onboarding@resend.dev>"):
    """Send email via Resend API."""
    try:
        resp = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": from_addr,
                "to": [to],
                "subject": subject,
                "text": body,
            },
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def notify_bid_awarded(to: str, job_title: str, amount: str, job_id: str, *, api_key: str):
    send_email(
        to=to,
        subject=f"[NEAR Agent] Bid Won: {job_title}",
        body=(
            f"Your bid was awarded!\n\n"
            f"Job: {job_title}\n"
            f"Amount: {amount} NEAR\n"
            f"Job ID: {job_id}\n\n"
            f"The agent is now generating a deliverable using multi-pass execution.\n"
            f"You will receive another email with the deliverable preview before submission.\n"
        ),
        api_key=api_key,
    )


def notify_deliverable_ready(to: str, job_title: str, job_id: str, preview: str, quality_score: int, *, api_key: str):
    send_email(
        to=to,
        subject=f"[NEAR Agent] Deliverable Ready (Score: {quality_score}/100): {job_title}",
        body=(
            f"Deliverable generated and self-reviewed.\n\n"
            f"Job: {job_title}\n"
            f"Job ID: {job_id}\n"
            f"Quality Score: {quality_score}/100\n\n"
            f"--- DELIVERABLE PREVIEW (first 2000 chars) ---\n\n"
            f"{preview[:2000]}\n\n"
            f"--- END PREVIEW ---\n\n"
            f"The agent will auto-submit in 10 minutes unless you stop it:\n"
            f"  ssh root@46.224.186.172 systemctl stop near-agent\n"
        ),
        api_key=api_key,
    )


def notify_submitted(to: str, job_title: str, job_id: str, amount: str, *, api_key: str):
    send_email(
        to=to,
        subject=f"[NEAR Agent] Work Submitted: {job_title}",
        body=(
            f"Deliverable has been submitted.\n\n"
            f"Job: {job_title}\n"
            f"Job ID: {job_id}\n"
            f"Payment: {amount} NEAR (in escrow, released on acceptance)\n\n"
            f"Waiting for the job creator to review and accept.\n"
            f"If they request changes, the agent will handle it next cycle.\n"
        ),
        api_key=api_key,
    )


def notify_error(to: str, job_title: str, job_id: str, error: str, *, api_key: str):
    send_email(
        to=to,
        subject=f"[NEAR Agent] Error: {job_title}",
        body=(
            f"Something went wrong.\n\n"
            f"Job: {job_title}\n"
            f"Job ID: {job_id}\n"
            f"Error: {error}\n\n"
            f"You may need to intervene manually.\n"
        ),
        api_key=api_key,
    )
