import json
import os
from pathlib import Path

import requests


def resolve_job_id() -> str:
    """Resolve job ID from env or GitHub event payload.

    Priority:
    1) JOB_ID env var (set by workflow env)
    2) repository_dispatch payload: github.event.client_payload.job_id
    3) workflow_dispatch input: github.event.inputs.job_id
    """
    if os.environ.get("JOB_ID"):
        return os.environ["JOB_ID"]

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise RuntimeError("JOB_ID is missing and GITHUB_EVENT_PATH is unavailable")

    event_data = json.loads(Path(event_path).read_text(encoding="utf-8"))

    job_id = (
        (event_data.get("client_payload") or {}).get("job_id")
        or (event_data.get("inputs") or {}).get("job_id")
    )

    if not job_id:
        raise RuntimeError(
            "JOB_ID not found in env, client_payload.job_id, or inputs.job_id"
        )

    return job_id


def get_supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    if not url:
        raise RuntimeError("Missing SUPABASE_URL (or NEXT_PUBLIC_SUPABASE_URL)")
    return url.rstrip("/")


JOB_ID = resolve_job_id()
SUPABASE_URL = get_supabase_url()
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


def patch_job(fields: dict) -> None:
    response = requests.patch(
        f"{SUPABASE_URL}/rest/v1/video_jobs?id=eq.{JOB_ID}",
        headers=HEADERS,
        json=fields,
        timeout=30,
    )
    response.raise_for_status()


def fetch_job() -> dict:
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/video_jobs?id=eq.{JOB_ID}",
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise RuntimeError(f"No video_jobs row found for JOB_ID={JOB_ID}")
    return rows[0]


def insert_windows(rows: list[dict]) -> None:
    if not rows:
        return

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/match_windows",
        headers=HEADERS,
        json=rows,
        timeout=30,
    )
    response.raise_for_status()


def insert_points(rows: list[dict]) -> None:
    if not rows:
        return

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/match_points",
        headers=HEADERS,
        json=rows,
        timeout=30,
    )
    response.raise_for_status()


def main() -> None:
    patch_job({"status": "processing", "error": None})
    try:
        job = fetch_job()

        # TODO Stage A: download video, extract audio (transient /tmp files)
        # TODO Stage B: whistle detection -> whistle_timestamps
        # TODO Stage C: camera-cut detection -> cut_timestamps
        # TODO Stage D: classify windows + apply job['known_events'] overrides
        # TODO Stage E: Gemini calls (anchor vs routine)
        # TODO Stage F: derive match_points from resolved windows

        # Temporary no-op outputs so the workflow is testable end-to-end.
        windows: list[dict] = []
        points: list[dict] = []

        insert_windows(windows)
        insert_points(points)

        patch_job({
            "status": "done",
            "error": None,
        })

        print(f"Job {JOB_ID} processed in scaffold mode for video: {job.get('video_url')}")
    except Exception as exc:
        patch_job({"status": "failed", "error": str(exc)[:1000]})
        raise


if __name__ == "__main__":
    main()
