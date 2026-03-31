#!/usr/bin/env python3
"""
Sarnia Brigade Season Summary Scraper
======================================
Fetches per-team game results and practice counts from sarniabrigade.ca and
writes docs/data.json, which is consumed by the grid display page.

Data sources
------------
  Practices  — public iCalendar feed: /webcal.ashx?IDs=<teamId>
               Any VEVENT whose SUMMARY contains "practice" is counted.
  Game results — HTML schedule pages: /Teams/<id>/Schedule/?Month=N&Year=N
               Result/score text is extracted from the compressed inline HTML.

NOTE: Score parsing uses regex against the MBSportsWeb HTML structure.
      If result or score data looks wrong once games begin, update the
      RESULT_RE / SCORE_RE patterns in parse_schedule() below.
"""

import json
import re
import sys
from datetime import datetime, date, timezone
from pathlib import Path
import os
import urllib.parse
from collections import defaultdict
import urllib.request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL     = "https://sarniabrigade.ca"
ICS_FEED     = BASE_URL + "/webcal.ashx?IDs={team_id}"
SCHEDULE_URL = BASE_URL + "/Teams/{team_id}/Schedule/?Month={month}&Year={year}"
COACHES_URL  = BASE_URL + "/Teams/{team_id}/Coaches/"
CP_LOGIN_URL = BASE_URL + "/Account/LogIn/"
CP_ROOT_URL  = BASE_URL + "/CP/"
CP_OFFICIALS_DASHBOARD_URL = BASE_URL + "/CP/#Module=Officials;SelectedValue=Content/Officials/Dashboard.aspx"
CP_OFFICIALS_SCHEDULE_URL = BASE_URL + "/CP/#Module=Officials;SelectedValue=Content/Officials/Schedule.aspx"

SEASON_YEAR   = 2026
SEASON_MONTHS = list(range(4, 10))   # April – September


# All 2026 roster teams discovered from /Seasons/Current/ and /Sitemap/
TEAMS = [
    # OBA Rep
    {"id": 1290, "name": "8U OBA Rep",           "category": "OBA Rep"},
    {"id": 1291, "name": "9U OBA Rep",            "category": "OBA Rep"},
    {"id": 1292, "name": "10U AA OBA Rep",        "category": "OBA Rep"},
    {"id": 1311, "name": "10U A OBA Rep",         "category": "OBA Rep"},
    {"id": 1293, "name": "11U OBA Rep",           "category": "OBA Rep"},
    {"id": 1294, "name": "12U OBA Rep",           "category": "OBA Rep"},
    {"id": 1295, "name": "13U OBA Rep",           "category": "OBA Rep"},
    {"id": 1296, "name": "14U OBA Rep",           "category": "OBA Rep"},
    {"id": 1297, "name": "15U OBA Rep",           "category": "OBA Rep"},
    # Select
    {"id": 1299, "name": "9U Select",             "category": "Select"},
    {"id": 1303, "name": "11U Select",            "category": "Select"},
    {"id": 1300, "name": "13U Select",            "category": "Select"},
    {"id": 1301, "name": "15U Select",            "category": "Select"},
    # River League
    {"id": 1304, "name": "9U River League",       "category": "River League"},
    {"id": 1310, "name": "11U Lady Brigade",      "category": "River League"},
    {"id": 1315, "name": "11U River League",      "category": "River League"},
    # House League
    {"id": 1302, "name": "13U LDBA House League", "category": "House League"},
    # Senior / Other
    {"id": 1298, "name": "16U PBLO",              "category": "Senior"},
    {"id": 1306, "name": "22U AAA",               "category": "Senior"},
    {"id": 1307, "name": "Senior AAA",            "category": "Senior"},
    {"id": 1305, "name": "Instructional",         "category": "Instructional"},
]
TEAM_NAME_TO_ID = {team["name"]: team["id"] for team in TEAMS}

CP_GAME_ROW_RE = re.compile(
    r"^(?P<marker>DH)?\t?(?P<date>(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+[A-Z][a-z]{2}\s+\d{2})"
    r"\t(?P<time>\d{1,2}:\d{2}\s+[AP]M)\t(?P<category>[^\t]*)\t(?P<team>[^\t]+)"
    r"\t(?P<opponent>[^\t]+)\t(?P<venue>[^\t]+)\t(?P<description>[^\n]+)$"
)
CP_OFFICIAL_RE = re.compile(
    r"^(?P<name>.+?)\s+\((?P<role>Home Plate|Bases|Scorekeeper)\),\s*\$(?P<pay>[0-9.]+)$"
)

ASSIGNMENT_STATE_NO_OFFICIALS = "no_officials_assigned"
ASSIGNMENT_STATE_NOT_ACCEPTED = "assigned_not_accepted"
ASSIGNMENT_STATE_DENIED = "assigned_but_denied"
ASSIGNMENT_STATE_ACCEPTED = "assigned_and_accepted"


def infer_official_status(raw_line: str) -> str:
    """Infer official acceptance status from textual markers when available.

    CP text exports do not always include explicit status labels. We still parse
    known markers when present and default to accepted to preserve existing
    behavior until richer status signals are collected.
    """
    text = str(raw_line or "").strip().lower()
    if not text:
        return "accepted"

    if any(token in text for token in ["denied", "declined", "decline"]):
        return "denied"
    if any(token in text for token in ["not accepted", "pending", "unaccepted", "awaiting acceptance"]):
        return "pending"
    if "accepted" in text:
        return "accepted"
    return "accepted"


def infer_official_status_from_class_name(class_name: str) -> str:
    """Infer status from CP CSS class names on official rows."""
    tokens = set(str(class_name or "").strip().lower().split())
    if "denied" in tokens:
        return "denied"
    if "unconfirmed" in tokens:
        return "pending"
    if "confirmed" in tokens:
        return "accepted"
    return "unknown"


def classify_game_assignment_state(assigned_count: int, accepted_count: int, pending_count: int, denied_count: int) -> str:
    """Return one game-level assignment state.

    Rule confirmed with the user: if any accepted official exists, classify the
    game as accepted even if denied officials are also listed.
    """
    if assigned_count <= 0:
        return ASSIGNMENT_STATE_NO_OFFICIALS
    if accepted_count > 0:
        return ASSIGNMENT_STATE_ACCEPTED
    if denied_count > 0:
        return ASSIGNMENT_STATE_DENIED
    if pending_count > 0:
        return ASSIGNMENT_STATE_NOT_ACCEPTED
    return ASSIGNMENT_STATE_NOT_ACCEPTED

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def fetch(url: str) -> str:
    """GET url and return decoded text; returns '' on any error."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "SarniaBrigadeStatBot/1.0 "
                    "(+https://github.com/robwinship/sarnia-minor-brigade-stats)"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  WARN  {url}\n        {exc}", file=sys.stderr)
        return ""


def fetch_with_opener(opener: urllib.request.OpenerDirector, url: str, data=None) -> str:
    """GET/POST with an opener; returns decoded text or ''."""
    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": (
                    "SarniaBrigadeStatBot/1.0 "
                    "(+https://github.com/robwinship/sarnia-minor-brigade-stats)"
                )
            },
        )
        with opener.open(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  WARN  {url}\n        {exc}", file=sys.stderr)
        return ""


def build_http_opener() -> urllib.request.OpenerDirector:
    """Create an opener with cookie support for CP login attempts."""
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    cookie_handler = urllib.request.HTTPCookieProcessor(jar)
    return urllib.request.build_opener(cookie_handler)


def login_cp_http(opener: urllib.request.OpenerDirector, username: str, password: str) -> bool:
    """Attempt CP login via HTTP form post. Returns True on probable success."""
    login_page = fetch_with_opener(opener, CP_LOGIN_URL)
    if not login_page:
        return False

    payload = urllib.parse.urlencode({
        "Username": username,
        "Password": password,
        "RememberMe": "false",
    }).encode("utf-8")
    _ = fetch_with_opener(opener, CP_LOGIN_URL, data=payload)

    cp_page = fetch_with_opener(opener, CP_ROOT_URL)
    if not cp_page:
        return False
    # Heuristic: logged-out pages typically expose obvious login markers.
    return "Account/LogIn" not in cp_page and "name=\"Password\"" not in cp_page


def format_cp_toolbar_date(iso_date: str) -> str:
    """Convert YYYY-MM-DD into the CP toolbar date label format."""
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    return dt.strftime("%a %b %d")


def fetch_cp_schedule_text(username: str, password: str, start_date: str, end_date: str) -> tuple[str, str]:
    """Log in via Playwright and return the Officials schedule table text."""
    if not username or not password:
        return "", "missing_credentials"

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return "", "playwright_unavailable"

    start_label = format_cp_toolbar_date(start_date)
    end_label = format_cp_toolbar_date(end_date)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(CP_LOGIN_URL, wait_until="load", timeout=60000)
            page.locator("#UserName").fill(username)
            page.locator("#Password").fill(password)
            page.locator("#LoginButton").click()
            page.wait_for_timeout(3000)

            if "Account/LogIn" in page.url or "Account/Login" in page.url:
                browser.close()
                return "", "login_failed"

            page.goto(CP_OFFICIALS_DASHBOARD_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            nav = next((frame for frame in page.frames if frame.name == "rpNavMain"), None)
            main = next((frame for frame in page.frames if frame.name == "rpMain"), None)
            if nav is None or main is None:
                browser.close()
                return "", "officials_frames_not_found"

            nav.locator("span.rtIn", has_text="Standard Games Lists").click()
            page.wait_for_timeout(1500)
            nav.locator("span.rtIn", has_text="All Games").click()
            page.wait_for_timeout(5000)

            start_input = main.locator("#ctl00_ctl00_cMain_cTop_rtbTop_i6_rdpStartDate_dateInput")
            end_input = main.locator("#ctl00_ctl00_cMain_cTop_rtbTop_i6_rdpEndDate_dateInput")
            start_input.click()
            start_input.press("Control+A")
            start_input.type(start_label)
            end_input.click()
            end_input.press("Control+A")
            end_input.type(end_label)
            main.locator("span.rtbText", has_text="Update").click()
            page.wait_for_timeout(8000)

            body_text = main.locator("body").inner_text(timeout=10000)
            browser.close()
            if "All Scheduled Games" not in body_text:
                return "", "schedule_grid_not_found"
            return body_text, ""
    except Exception as exc:
        return "", f"playwright_error:{exc}"


def fetch_cp_schedule_rows(username: str, password: str, start_date: str, end_date: str) -> tuple[list, str]:
    """Log in via Playwright and return structured Officials schedule rows.

    The CP table includes class names like "gameOfficial confirmed" and
    "gameOfficial unconfirmed" that are not available in plain-text exports.
    """
    if not username or not password:
        return [], "missing_credentials"

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return [], "playwright_unavailable"

    start_label = format_cp_toolbar_date(start_date)
    end_label = format_cp_toolbar_date(end_date)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(CP_LOGIN_URL, wait_until="load", timeout=60000)
            page.locator("#UserName").fill(username)
            page.locator("#Password").fill(password)
            page.locator("#LoginButton").click()
            page.wait_for_timeout(3000)

            if "Account/LogIn" in page.url or "Account/Login" in page.url:
                browser.close()
                return [], "login_failed"

            page.goto(CP_OFFICIALS_DASHBOARD_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            nav = next((frame for frame in page.frames if frame.name == "rpNavMain"), None)
            main = next((frame for frame in page.frames if frame.name == "rpMain"), None)
            if nav is None or main is None:
                browser.close()
                return [], "officials_frames_not_found"

            nav.locator("span.rtIn", has_text="Standard Games Lists").click()
            page.wait_for_timeout(1500)
            nav.locator("span.rtIn", has_text="All Games").click()
            page.wait_for_timeout(5000)

            start_input = main.locator("#ctl00_ctl00_cMain_cTop_rtbTop_i6_rdpStartDate_dateInput")
            end_input = main.locator("#ctl00_ctl00_cMain_cTop_rtbTop_i6_rdpEndDate_dateInput")
            start_input.click()
            start_input.press("Control+A")
            start_input.type(start_label)
            end_input.click()
            end_input.press("Control+A")
            end_input.type(end_label)
            main.locator("span.rtbText", has_text="Update").click()
            page.wait_for_timeout(8000)

            structured_rows = main.evaluate(
                """
                () => {
                  const rows = [...document.querySelectorAll('tr')];
                  const results = [];
                  let current = null;

                  const dateRe = /^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\\s+[A-Z][a-z]{2}\\s+\\d{2}$/;
                  const timeRe = /^\\d{1,2}:\\d{2}\\s+[AP]M$/;

                  for (const tr of rows) {
                    const cells = [...tr.querySelectorAll('td')];
                    const cellTexts = cells.map(td => (td.innerText || '').replace(/\\s+/g, ' ').trim());

                    const dateIndex = cellTexts.findIndex(text => dateRe.test(text));
                    const timeIndex = cellTexts.findIndex(text => timeRe.test(text));
                    const isGameRow = dateIndex !== -1 && timeIndex !== -1;

                    if (isGameRow) {
                      current = {
                        cell_texts: cellTexts,
                        raw_row_text: (tr.innerText || '').replace(/\\s+/g, ' ').trim(),
                        no_officials: false,
                        officials: [],
                      };
                      results.push(current);
                    }

                    if (!current) {
                      continue;
                    }

                    if (/No officials assigned/i.test(tr.innerText || '')) {
                      current.no_officials = true;
                    }

                    const officials = [...tr.querySelectorAll('.gameOfficial')];
                    for (const officialEl of officials) {
                      current.officials.push({
                        text: (officialEl.innerText || '').replace(/\\s+/g, ' ').trim(),
                        class_name: (officialEl.className || '').trim(),
                      });
                    }
                  }

                  return results;
                }
                """
            )
            browser.close()

            if not structured_rows:
                return [], "schedule_grid_not_found"
            return structured_rows, ""
    except Exception as exc:
        return [], f"playwright_error:{exc}"


def parse_cp_umpire_assignments_from_rows(structured_rows: list) -> list:
    """Parse structured CP table rows into assignment rows."""
    if not structured_rows:
        return []

    parsed = []
    for row in structured_rows:
        cell_texts = [str(text or "").strip() for text in (row.get("cell_texts") or [])]
        if not cell_texts:
            continue

        date_index = next((i for i, text in enumerate(cell_texts) if re.match(r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+[A-Z][a-z]{2}\s+\d{2}$", text)), -1)
        time_index = next((i for i, text in enumerate(cell_texts) if re.match(r"^\d{1,2}:\d{2}\s+[AP]M$", text)), -1)
        if date_index == -1 or time_index == -1:
            continue

        team_name = cell_texts[time_index + 2].strip() if len(cell_texts) > time_index + 2 else ""
        team_id = TEAM_NAME_TO_ID.get(team_name)
        if team_id is None:
            continue

        officials = []
        for official in row.get("officials") or []:
            text = str(official.get("text") or "").strip()
            if not text:
                continue
            official_match = CP_OFFICIAL_RE.match(text)
            if not official_match:
                continue

            class_name = str(official.get("class_name") or "").strip()
            class_status = infer_official_status_from_class_name(class_name)
            text_status = infer_official_status(text)
            status = class_status if class_status != "unknown" else text_status

            officials.append({
                "name": official_match.group("name").strip(),
                "role": official_match.group("role").strip(),
                "pay": float(official_match.group("pay")),
                "status": status,
                "status_source": "class" if class_status != "unknown" else "text",
            })

        no_officials_flag = bool(row.get("no_officials"))
        status_counts = defaultdict(int)
        for official in officials:
            status_counts[str(official.get("status") or "accepted").strip().lower()] += 1

        assigned_count = len(officials)
        accepted_count = status_counts.get("accepted", 0)
        pending_count = status_counts.get("pending", 0)
        denied_count = status_counts.get("denied", 0)
        assignment_state = ASSIGNMENT_STATE_NO_OFFICIALS if no_officials_flag else classify_game_assignment_state(
            assigned_count=assigned_count,
            accepted_count=accepted_count,
            pending_count=pending_count,
            denied_count=denied_count,
        )

        date_text = cell_texts[date_index]
        parsed_date = datetime.strptime(f"{date_text} {SEASON_YEAR}", "%a %b %d %Y").date().isoformat()
        parsed.append({
            "team_id": team_id,
            "team_name": team_name,
            "date": parsed_date,
            "time": cell_texts[time_index].strip() if len(cell_texts) > time_index else "",
            "opponent": cell_texts[time_index + 3].strip() if len(cell_texts) > time_index + 3 else "",
            "venue": cell_texts[time_index + 4].strip() if len(cell_texts) > time_index + 4 else "",
            "game_id": None,
            "umpires": officials,
            "doubleheader_flag": False,
            "assignment_state": assignment_state,
            "assigned_count": assigned_count,
            "accepted_count": accepted_count,
            "pending_count": pending_count,
            "denied_count": denied_count,
        })

    return parsed


def parse_cp_umpire_assignments(schedule_text: str) -> list:
    """Parse Officials schedule text into structured assignment rows.

    Expected row shape:
      {
        "team_id": int,
        "team_name": str,
        "date": "YYYY-MM-DD",
        "time": str,
        "opponent": str,
        "venue": str,
        "game_id": str | None,
        "umpires": [{"name": str, "role": str}],
      }
    """
    if not schedule_text or "Game #\tDate\tTime\tCategory\tTeam\tOpponent\tVenue\tDescription" not in schedule_text:
        return []

    body = schedule_text.split("Game #\tDate\tTime\tCategory\tTeam\tOpponent\tVenue\tDescription", 1)[1]
    block_starts = [match.start() for match in re.finditer(
        r"(?m)^(?:DH\t|\t)(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+[A-Z][a-z]{2}\s+\d{2}\t\d{1,2}:\d{2}\s+[AP]M\t",
        body,
    )]
    if not block_starts:
        return []

    blocks = []
    for idx, start in enumerate(block_starts):
        end = block_starts[idx + 1] if idx + 1 < len(block_starts) else len(body)
        blocks.append(body[start:end].strip())

    parsed = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        header_line = lines[0].replace("\xa0", "").rstrip()
        header_match = CP_GAME_ROW_RE.match(header_line)
        if not header_match:
            continue

        team_name = header_match.group("team").strip()
        team_id = TEAM_NAME_TO_ID.get(team_name)
        if team_id is None:
            continue

        umpires = []
        no_officials_flag = False
        for raw_line in lines[1:]:
            if raw_line == "No officials assigned":
                umpires = []
                no_officials_flag = True
                break
            official_match = CP_OFFICIAL_RE.match(raw_line)
            if not official_match:
                continue
            umpires.append({
                "name": official_match.group("name").strip(),
                "role": official_match.group("role").strip(),
                "pay": float(official_match.group("pay")),
                "status": infer_official_status(raw_line),
            })

        status_counts = defaultdict(int)
        for umpire in umpires:
            status = str(umpire.get("status") or "accepted").strip().lower()
            status_counts[status] += 1

        assigned_count = len(umpires)
        accepted_count = status_counts.get("accepted", 0)
        pending_count = status_counts.get("pending", 0)
        denied_count = status_counts.get("denied", 0)
        assignment_state = ASSIGNMENT_STATE_NO_OFFICIALS if no_officials_flag else classify_game_assignment_state(
            assigned_count=assigned_count,
            accepted_count=accepted_count,
            pending_count=pending_count,
            denied_count=denied_count,
        )

        date_text = header_match.group("date").strip()
        parsed_date = datetime.strptime(f"{date_text} {SEASON_YEAR}", "%a %b %d %Y").date().isoformat()
        parsed.append({
            "team_id": team_id,
            "team_name": team_name,
            "date": parsed_date,
            "time": header_match.group("time").strip(),
            "opponent": header_match.group("opponent").strip(),
            "venue": header_match.group("venue").strip(),
            "game_id": None,
            "umpires": umpires,
            "doubleheader_flag": bool(header_match.group("marker")),
            "assignment_state": assignment_state,
            "assigned_count": assigned_count,
            "accepted_count": accepted_count,
            "pending_count": pending_count,
            "denied_count": denied_count,
        })

    return parsed


def compute_umpire_issues(games: list, assignments: list, data_available: bool, unavailable_reason: str) -> dict:
    """Compute umpire issue metrics for one team."""
    issues = {
        "games_missed": 0,
        "games_missed_upcoming": 0,
        "doubleheader_mismatch": 0,
        "doubleheader_mismatch_upcoming": 0,
        "data_available": False,
        "unavailable_reason": unavailable_reason or "umpire_data_unavailable",
        "games_missed_details": [],
        "doubleheader_mismatch_details": [],
    }
    if not data_available:
        return issues

    issues["data_available"] = True
    issues["unavailable_reason"] = ""
    if not assignments:
        return issues

    today_iso = date.today().isoformat()

    normalized = []
    for row in assignments:
        date_text = str(row.get("date") or "").strip()
        if not date_text:
            continue
        # Keep only valid ISO dates from CP parser output.
        try:
            datetime.strptime(date_text, "%Y-%m-%d")
        except ValueError:
            continue

        assigned_names = []
        accepted_names = []
        pending_names = []
        denied_names = []
        for umpire in row.get("umpires") or []:
            if isinstance(umpire, dict):
                name = str(umpire.get("name") or "").strip()
                status = str(umpire.get("status") or "accepted").strip().lower()
            else:
                name = str(umpire or "").strip()
                status = "accepted"
            if name:
                assigned_names.append(name)
                if status == "accepted":
                    accepted_names.append(name)
                elif status == "pending":
                    pending_names.append(name)
                elif status == "denied":
                    denied_names.append(name)

        assigned_uniq = sorted(set(assigned_names))
        accepted_uniq = sorted(set(accepted_names))
        pending_uniq = sorted(set(pending_names))
        denied_uniq = sorted(set(denied_names))

        issue_timing = "past" if date_text < today_iso else "upcoming"
        assignment_state = classify_game_assignment_state(
            assigned_count=len(assigned_uniq),
            accepted_count=len(accepted_uniq),
            pending_count=len(pending_uniq),
            denied_count=len(denied_uniq),
        )

        normalized.append({
            "date": date_text,
            "time": str(row.get("time") or "").strip(),
            "opponent": str(row.get("opponent") or "").strip(),
            "venue": str(row.get("venue") or "").strip(),
            "game_id": row.get("game_id"),
            "umpires": assigned_uniq,
            "accepted_umpires": accepted_uniq,
            "pending_umpires": pending_uniq,
            "denied_umpires": denied_uniq,
            "assignment_state": assignment_state,
            "issue_timing": issue_timing,
        })

    games_missed_details = []
    past_games_missed = 0
    upcoming_games_missed = 0
    for row in normalized:
        if len(row["accepted_umpires"]) >= 2:
            continue

        detail = {
            "date": row["date"],
            "time": row["time"],
            "opponent": row["opponent"],
            "venue": row["venue"],
            "assigned_umpires": row["umpires"],
            "accepted_umpires": row["accepted_umpires"],
            "pending_umpires": row["pending_umpires"],
            "denied_umpires": row["denied_umpires"],
            "assigned_count": len(row["umpires"]),
            "accepted_count": len(row["accepted_umpires"]),
            "pending_count": len(row["pending_umpires"]),
            "denied_count": len(row["denied_umpires"]),
            "assignment_state": row["assignment_state"],
            "issue_timing": row["issue_timing"],
        }
        games_missed_details.append(detail)

        if row["issue_timing"] == "past":
            past_games_missed += 1
        else:
            upcoming_games_missed += 1

    games_missed_details.sort(key=lambda item: (
        item.get("date") or "",
        item.get("time") or "",
        item.get("opponent") or "",
    ))
    issues["games_missed"] = past_games_missed
    issues["games_missed_upcoming"] = upcoming_games_missed
    issues["games_missed_details"] = games_missed_details

    by_date = defaultdict(list)
    for row in normalized:
        if row.get("date"):
            by_date[row["date"]].append(row)

    past_mismatch_count = 0
    upcoming_mismatch_count = 0
    mismatch_details = []
    for date_text, rows in by_date.items():
        if len(rows) < 2:
            continue
        pairs = []
        incomplete = False
        for row in rows:
            if len(row["accepted_umpires"]) != 2:
                incomplete = True
            else:
                pairs.append(tuple(row["accepted_umpires"]))

        unique_pairs = set(pairs)
        mismatch_found = incomplete or len(unique_pairs) > 1
        if not mismatch_found:
            continue

        # Names that are not consistent across all games for this date.
        name_frequency = defaultdict(int)
        for row in rows:
            for name in set(row["accepted_umpires"]):
                name_frequency[name] += 1
        mismatched_names = sorted([
            name for name, count in name_frequency.items()
            if count < len(rows)
        ])

        issue_timing = "past" if date_text < today_iso else "upcoming"
        if issue_timing == "past":
            past_mismatch_count += 1
        else:
            upcoming_mismatch_count += 1

        mismatch_details.append({
            "date": date_text,
            "issue_timing": issue_timing,
            "incomplete_assignment": incomplete,
            "pair_signatures": [" | ".join(pair) for pair in sorted(unique_pairs)],
            "mismatched_names": mismatched_names,
            "games": [
                {
                    "time": row["time"],
                    "opponent": row["opponent"],
                    "venue": row["venue"],
                    "assigned_umpires": row["umpires"],
                    "accepted_umpires": row["accepted_umpires"],
                    "pending_umpires": row["pending_umpires"],
                    "denied_umpires": row["denied_umpires"],
                    "assigned_count": len(row["umpires"]),
                    "accepted_count": len(row["accepted_umpires"]),
                    "pending_count": len(row["pending_umpires"]),
                    "denied_count": len(row["denied_umpires"]),
                    "assignment_state": row["assignment_state"],
                }
                for row in sorted(rows, key=lambda r: ((r.get("time") or ""), (r.get("opponent") or "")))
            ],
        })

    mismatch_details.sort(key=lambda item: item.get("date") or "")
    issues["doubleheader_mismatch"] = past_mismatch_count
    issues["doubleheader_mismatch_upcoming"] = upcoming_mismatch_count
    issues["doubleheader_mismatch_details"] = mismatch_details
    return issues


def collect_cp_umpire_assignments() -> tuple[dict, dict]:
    """Collect umpire assignments keyed by team id with status metadata."""
    username = os.getenv("CP_USERNAME", "").strip()
    password = os.getenv("CP_PASSWORD", "").strip()

    status = {
        "available": False,
        "reason": "not_attempted",
        "source_url": CP_OFFICIALS_SCHEDULE_URL,
    }
    if not username or not password:
        status["reason"] = "missing_credentials"
        return {}, status

    structured_rows, reason = fetch_cp_schedule_rows(
        username,
        password,
        f"{SEASON_YEAR}-04-01",
        f"{SEASON_YEAR}-09-30",
    )
    parsed_rows = parse_cp_umpire_assignments_from_rows(structured_rows)

    # Fallback to existing text parser if DOM structure changes.
    if not parsed_rows:
        schedule_text, text_reason = fetch_cp_schedule_text(
            username,
            password,
            f"{SEASON_YEAR}-04-01",
            f"{SEASON_YEAR}-09-30",
        )
        if not schedule_text:
            status["reason"] = reason or text_reason or "fetch_failed"
            return {}, status
        parsed_rows = parse_cp_umpire_assignments(schedule_text)

    if not parsed_rows:
        status["reason"] = "officials_page_parsed_no_assignments"
        return {}, status

    by_team_id = defaultdict(list)
    for row in parsed_rows:
        team_id = row.get("team_id")
        if team_id is None:
            continue
        by_team_id[int(team_id)].append(row)

    status["available"] = True
    status["reason"] = "ok"
    return dict(by_team_id), status

# ---------------------------------------------------------------------------
# ICS / iCalendar parsing  (practices)
# ---------------------------------------------------------------------------

def _unfold_ics(text: str) -> str:
    """Unwrap iCalendar line continuations (RFC 5545 §3.1)."""
    return re.sub(r"\r?\n[ \t]", "", text)


def classify_event(summary: str) -> str:
    text = summary.lower()
    if "practice" in text:
        return "practice"
    # Keep exhibition games bundled with regular games.
    if re.search(r"\b(vs\.?|@|game|exhibition|doubleheader|scrimmage)\b", text):
        return "game"
    return "other"


def parse_ics_start(raw_dt: str):
    """Return (YYYY-MM-DD, h:mm AM/PM) from DTSTART-like values.

    DTSTART values ending in 'Z' are UTC; convert to local machine time
    (the scraper runs in the Eastern timezone alongside the rest of the app).
    Values without 'Z' are treated as already in local time.
    """
    raw = (raw_dt or "").strip()
    date_m = re.match(r"^(\d{4})(\d{2})(\d{2})", raw)
    if not date_m:
        return None, None

    y, mo, d = date_m.groups()

    # All-day events only contain YYYYMMDD (no time component).
    time_m = re.search(r"T(\d{2})(\d{2})(\d{2})(Z?)", raw)
    if not time_m:
        return f"{y}-{mo}-{d}", None

    hh, mm = int(time_m.group(1)), int(time_m.group(2))
    is_utc = time_m.group(4) == "Z"

    if is_utc:
        # Convert UTC → local time so displayed times match Eastern clocks.
        dt_utc = datetime(int(y), int(mo), int(d), hh, mm, tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone()          # uses the OS timezone (Eastern)
        date_text = dt_local.date().isoformat()
        lh, lm = dt_local.hour, dt_local.minute
    else:
        date_text = f"{y}-{mo}-{d}"
        lh, lm = hh, mm

    suffix = "AM" if lh < 12 else "PM"
    hour12 = lh % 12 or 12
    return date_text, f"{hour12}:{lm:02d} {suffix}"


def parse_ics_events(text: str) -> list:
    """Parse dated VEVENT records from a public iCalendar team feed."""
    if not text or "BEGIN:VCALENDAR" not in text:
        return []

    text = _unfold_ics(text)
    events = []
    for block in re.split(r"BEGIN:VEVENT\r?\n", text)[1:]:
        summary_m = re.search(r"^SUMMARY:(.*?)$", block, re.MULTILINE)
        start_m = re.search(r"^DTSTART[^\n:]*:([^\n]+)$", block, re.MULTILINE)
        end_m = re.search(r"^DTEND[^\n:]*:(\d{8})(?:T\d{6}Z?)?", block, re.MULTILINE)
        location_m = re.search(r"^LOCATION:(.*?)$", block, re.MULTILINE)
        uid_m = re.search(r"^UID:(.*?)$", block, re.MULTILINE)
        desc_m = re.search(r"^DESCRIPTION:(.*?)$", block, re.MULTILINE)
        status_m = re.search(r"^STATUS:(.*?)$", block, re.MULTILINE)

        if not start_m:
            continue

        start_raw = start_m.group(1).strip()
        start_date, start_time = parse_ics_start(start_raw)
        if not start_date:
            continue

        year = int(start_date[:4])
        if year != SEASON_YEAR:
            continue

        summary = summary_m.group(1).strip() if summary_m else ""
        location = location_m.group(1).strip() if location_m else ""
        end_date = None
        if end_m:
            end_raw = end_m.group(1)
            end_date = f"{end_raw[:4]}-{end_raw[4:6]}-{end_raw[6:8]}"

        # Tournament events have a /Tournaments/ URL in their DESCRIPTION.
        # Use that as the authoritative signal rather than relying on the
        # summary text (e.g. "Great Lakes World Series" has no keyword).
        description = desc_m.group(1).strip() if desc_m else ""
        if "/Tournaments/" in description:
            event_type = "tournament"
        else:
            event_type = classify_event(summary)

        cancelled = False
        if status_m:
            status_val = status_m.group(1).strip().upper()
            if status_val in ("CANCELLED", "CANCELED"):
                cancelled = True

        events.append({
            "uid": uid_m.group(1).strip() if uid_m else None,
            "date": start_date,
            "start_time": start_time,
            "end_date": end_date,
            "summary": summary,
            "location": location,
            "type": event_type,
            "cancelled": cancelled,
        })

    return events

# ---------------------------------------------------------------------------
# HTML schedule parsing  (game results)
# ---------------------------------------------------------------------------

# MBSportsWeb result patterns observed on live Sportsheadz sites:
#   "WIN 5 - 3"  "LOSS 2 - 7"  "TIE 4 - 4"
#   "W 5-3"      "L 2-7"
RESULT_RE = re.compile(
    r"\b(WIN|LOSS|TIE|WON|LOST|W|L|T)\b\s*(\d{1,2})\s*[-\u2013]\s*(\d{1,2})",
    re.IGNORECASE,
)
# Bare score without explicit result label (fallback)
SCORE_RE = re.compile(r"\b(\d{1,2})\s*[-\u2013]\s*(\d{1,2})\b")

VS_RE   = re.compile(r"\bvs\.?\s+([A-Za-z][A-Za-z0-9 .'\-]{1,45})", re.IGNORECASE)
AT_RE   = re.compile(r"@\s+([A-Za-z][A-Za-z0-9 .'\-]{1,45})", re.IGNORECASE)
TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\s*(AM|PM)\b", re.IGNORECASE)


def _strip_tags(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def parse_schedule(html: str, month: int, year: int) -> list:
    """
    Parse a team Schedule & Results HTML page.

    Strategy: the page content is minified to a single long line.
    Each game is anchored by an <a href="/Teams/N/Games/N/"> link.
    We split on those links and extract the text of each segment.
    """
    if not html:
        return []

    games = []
    # Split on every "Game Details" anchor; keep the separator via lookahead
    segments = re.split(r"(?=<a[^>]+href=\"/Teams/\d+/Games/\d+/\")", html)

    for seg in segments[1:]:
        # Extract game href and game_id
        href_m = re.match(r'<a[^>]+href="(/Teams/\d+/Games/(\d+)/)"', seg)
        if not href_m:
            continue
        game_href = href_m.group(1)
        game_id   = href_m.group(2)

        # Detect if this segment is marked as cancelled (look for class="cancelled" in a parent div)
        cancelled = False
        div_cancelled_m = re.search(r'<div[^>]*class="[^"]*cancelled[^"]*"', seg)
        if div_cancelled_m:
            cancelled = True

        # Grab text up to the next game anchor, venue block, or heading
        content_m = re.search(
            r'</a>(.*?)(?=<a[^>]+href="/Teams/\d+/Games/\d+/"|'
            r'<div class="heading|</div></div></div></main>|$)',
            seg, re.DOTALL,
        )
        raw_content = content_m.group(1) if content_m else seg[href_m.end():500]
        text = _strip_tags(raw_content)

        # --- Result + score ---
        result        = None
        brigade_score = None
        opp_score     = None

        rm = RESULT_RE.search(text)
        if rm:
            rw = rm.group(1).upper()
            result = (
                "W" if rw in ("WIN", "WON", "W") else
                "L" if rw in ("LOSS", "LOST", "L") else
                "T"
            )
            brigade_score = int(rm.group(2))
            opp_score     = int(rm.group(3))
        else:
            # Bare score — only use when the segment contains obvious game markers
            if re.search(r"\b(HOME GAME|AWAY GAME|vs\.?|@ )", text, re.IGNORECASE):
                sm = SCORE_RE.search(text)
                if sm:
                    brigade_score = int(sm.group(1))
                    opp_score     = int(sm.group(2))

        # --- Opponent + home/away ---
        # The schedule page marks each game with an explicit "HOME GAME" or
        # "AWAY GAME" badge. Use that as the primary signal; fall back to
        # vs./@ patterns for sites that may omit the badge.
        opponent = None
        is_home  = True

        vm = VS_RE.search(text)
        am = AT_RE.search(text)
        if vm:
            opponent = vm.group(1).strip().rstrip(".,;")
            is_home  = "AWAY GAME" not in text.upper()
        elif am:
            opponent = am.group(1).strip().rstrip(".,;")
            is_home  = False

        # --- Date ---
        game_date = None
        date_m = re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})\b", text)
        if date_m:
            try:
                game_date = date(year, month, int(date_m.group(1))).isoformat()
            except ValueError:
                game_date = None

        # Schedule pages display times in local Eastern time already.
        sched_time = None
        tm = TIME_RE.search(text)
        if tm:
            sched_time = f"{tm.group(1)} {tm.group(2).upper()}"

        games.append({
            "game_id":      game_id,
            "href":         BASE_URL + game_href,
            "date":         game_date,
            "start_time":   sched_time,
            "opponent":     opponent,
            "home":         is_home,
            "result":       result,
            "brigade_score": brigade_score,
            "opp_score":    opp_score,
            "cancelled":    cancelled,
        })

    return games


def parse_roster_counts(html: str) -> dict:
    """Parse player and adult role counts from a team Coaches page."""
    counts = {
        "players": 0,
        "adults": 0,
        "head_coaches": 0,
        "assistant_coaches": 0,
        "coaches": 0,
        "managers": 0,
    }
    if not html:
        return counts

    # Player profile links appear as /Players/<id>/, often duplicated for image/name.
    player_ids = set(re.findall(r"/Players/(\d+)/", html))
    counts["players"] = len(player_ids)

    # Roles are listed in the Coaching/Support section above Player Roster.
    # Restricting to this section avoids over-counting role words from elsewhere.
    text = _strip_tags(html)
    sec_m = re.search(r"Coaching Staff(.*?)Player Roster", text, re.IGNORECASE)
    if sec_m:
        section = sec_m.group(1)
    else:
        section = text

    counts["head_coaches"] = len(re.findall(r"\bHead Coach\b", section, re.IGNORECASE))
    counts["assistant_coaches"] = len(re.findall(r"\bAssistant Coach\b", section, re.IGNORECASE))
    counts["managers"] = len(re.findall(r"\bManager\b", section, re.IGNORECASE))

    coach_tokens = len(re.findall(r"\bCoach\b", section, re.IGNORECASE))
    plain_coach = coach_tokens - counts["head_coaches"] - counts["assistant_coaches"]
    counts["coaches"] = max(plain_coach, 0)

    counts["adults"] = (
        counts["head_coaches"]
        + counts["assistant_coaches"]
        + counts["coaches"]
        + counts["managers"]
    )
    return counts

# ---------------------------------------------------------------------------
# Per-team collection
# ---------------------------------------------------------------------------

def collect_team(team: dict, team_assignments: list, cp_status: dict) -> dict:
    out = {
        "id":           team["id"],
        "name":         team["name"],
        "category":     team["category"],
        "gp":      0,
        "wins":    0,
        "losses":  0,
        "ties":    0,
        "runs_for":     0,
        "runs_against": 0,
        "practices":    0,
        "roster": {
            "players": 0,
            "adults": 0,
            "head_coaches": 0,
            "assistant_coaches": 0,
            "coaches": 0,
            "managers": 0,
        },
        "events":       [],
        "games":        [],
        "umpire_issues": {
            "games_missed": 0,
            "games_missed_upcoming": 0,
            "doubleheader_mismatch": 0,
            "doubleheader_mismatch_upcoming": 0,
            "data_available": False,
            "unavailable_reason": cp_status.get("reason", "umpire_data_unavailable"),
            "games_missed_details": [],
            "doubleheader_mismatch_details": [],
        },
    }

    # -- Practices via ICS --------------------------------------------------
    print(f"  ICS    {team['name']} (id={team['id']}) …")
    ics_text = fetch(ICS_FEED.format(team_id=team["id"]))
    out["events"] = parse_ics_events(ics_text)
    out["practices"] = sum(1 for event in out["events"] if event["type"] == "practice")

    # -- Roster / personnel counts for insurance costing --------------------
    print(f"  ROSTER {team['name']} (id={team['id']}) …")
    coaches_html = fetch(COACHES_URL.format(team_id=team["id"]))
    out["roster"] = parse_roster_counts(coaches_html)

    # -- Game results via schedule HTML (month by month) --------------------
    for month in SEASON_MONTHS:
        url = SCHEDULE_URL.format(team_id=team["id"], month=month, year=SEASON_YEAR)
        print(f"  SCHED  {team['name']}  {SEASON_YEAR}-{month:02d} …")
        html = fetch(url)
        out["games"].extend(parse_schedule(html, month, SEASON_YEAR))

    # Deduplicate games by game_id
    seen, unique = set(), []
    for g in out["games"]:
        key = g.get("game_id") or g.get("href")
        if key and key not in seen:
            seen.add(key)
            unique.append(g)
    out["games"] = unique

    # Aggregate season totals
    for g in out["games"]:
        if g.get("result"):
            out["gp"] += 1
            if   g["result"] == "W": out["wins"]   += 1
            elif g["result"] == "L": out["losses"] += 1
            elif g["result"] == "T": out["ties"]   += 1
        if g.get("brigade_score") is not None:
            out["runs_for"]     += g["brigade_score"]
        if g.get("opp_score") is not None:
            out["runs_against"] += g["opp_score"]

    out["umpire_issues"] = compute_umpire_issues(
        out["games"],
        team_assignments,
        cp_status.get("available", False),
        cp_status.get("reason", "umpire_data_unavailable"),
    )

    return out

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    docs_dir = Path(__file__).resolve().parent.parent / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    out_path = docs_dir / "data.json"

    print("\n[CP Officials]")
    team_assignments, cp_status = collect_cp_umpire_assignments()
    if cp_status.get("available"):
        print("  INFO  Umpire assignment data collected successfully.")
    else:
        print(f"  WARN  Umpire assignment data unavailable ({cp_status.get('reason')}).")


    results = []
    cancellations = []
    for team in TEAMS:
        print(f"\n[{team['name']}]")
        try:
            team_data = collect_team(
                team,
                team_assignments.get(team["id"], []),
                cp_status,
            )
            results.append(team_data)
            # Aggregate cancelled events (games and practices)
            # Practices: look for event['cancelled'] or 'CANCELLED' in summary
            for event in team_data.get("events", []):
                if event.get("type") in ("practice", "game"):
                    if event.get("cancelled") or "CANCELLED" in event.get("summary", "").upper():
                        cancellations.append({
                            "team_id": team["id"],
                            "team_name": team["name"],
                            "type": event.get("type"),
                            "date": event.get("date"),
                            "start_time": event.get("start_time"),
                            "summary": event.get("summary"),
                            "location": event.get("location"),
                        })
            # Games: if any game has a 'cancelled' property or 'CANCELLED' in summary (if available)
            for game in team_data.get("games", []):
                if game.get("cancelled") or "CANCELLED" in str(game.get("summary", "")).upper():
                    cancellations.append({
                        "team_id": team["id"],
                        "team_name": team["name"],
                        "type": "game",
                        "date": game.get("date"),
                        "start_time": game.get("start_time"),
                        "summary": game.get("summary", ""),
                        "location": game.get("location", ""),
                    })
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)

    payload = {
        "season":    SEASON_YEAR,
        "season_start": f"{SEASON_YEAR}-01-01",
        "season_end": f"{SEASON_YEAR}-12-31",
        "generated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "umpire_data_status": cp_status,
        "teams":     results,
        "cancellations": cancellations,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    print(f"\n✓  Wrote {out_path}  ({len(results)} teams processed, {len(cancellations)} cancellations)")


if __name__ == "__main__":
    main()
