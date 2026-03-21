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
import urllib.request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL     = "https://sarniabrigade.ca"
ICS_FEED     = BASE_URL + "/webcal.ashx?IDs={team_id}"
SCHEDULE_URL = BASE_URL + "/Teams/{team_id}/Schedule/?Month={month}&Year={year}"

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
    {"id": 1316, "name": "13U River League",      "category": "River League"},
    # House League
    {"id": 1302, "name": "13U LDBA House League", "category": "House League"},
    # Senior / Other
    {"id": 1298, "name": "16U PBLO",              "category": "Senior"},
    {"id": 1306, "name": "22U AAA",               "category": "Senior"},
    {"id": 1307, "name": "Senior AAA",            "category": "Senior"},
    {"id": 1305, "name": "Instructional",         "category": "Instructional"},
]

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

        events.append({
            "uid": uid_m.group(1).strip() if uid_m else None,
            "date": start_date,
            "start_time": start_time,
            "end_date": end_date,
            "summary": summary,
            "location": location,
            "type": event_type,
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
        })

    return games

# ---------------------------------------------------------------------------
# Per-team collection
# ---------------------------------------------------------------------------

def collect_team(team: dict) -> dict:
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
        "events":       [],
        "games":        [],
    }

    # -- Practices via ICS --------------------------------------------------
    print(f"  ICS    {team['name']} (id={team['id']}) …")
    ics_text = fetch(ICS_FEED.format(team_id=team["id"]))
    out["events"] = parse_ics_events(ics_text)
    out["practices"] = sum(1 for event in out["events"] if event["type"] == "practice")

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

    return out

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    docs_dir = Path(__file__).resolve().parent.parent / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    out_path = docs_dir / "data.json"

    results = []
    for team in TEAMS:
        print(f"\n[{team['name']}]")
        try:
            results.append(collect_team(team))
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)

    payload = {
        "season":    SEASON_YEAR,
        "season_start": f"{SEASON_YEAR}-01-01",
        "season_end": f"{SEASON_YEAR}-12-31",
        "generated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "teams":     results,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    print(f"\n✓  Wrote {out_path}  ({len(results)} teams processed)")


if __name__ == "__main__":
    main()
