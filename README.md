# Sarnia Brigade — Season Stats

Per-team season summary for the [Sarnia Brigade Minor Baseball Association](https://www.sarniabrigade.ca).

## Live Page

> **[robwinship.github.io/sarnia-brigade-stats](https://robwinship.github.io/sarnia-brigade-stats)**

## What the grid shows

| Column | Description |
|--------|-------------|
| **GP** | Games played (completed games with a reported result) |
| **W / L / T** | Season wins, losses, and ties |
| **RF** | Runs scored by the Brigade team |
| **RA** | Runs scored by opponents |
| **+/−** | Run differential (RF − RA) |
| **Pct** | Win percentage |
| **Practice** | Running count of practices held so far this season |

Teams are grouped by division: OBA Rep · Select · River League · House League · Senior · Instructional.

## How it works

```
sarniabrigade.ca
       │
       ├── /webcal.ashx?IDs=<teamId>    ← iCalendar feed  → practice count
       └── /Teams/<id>/Schedule/        ← HTML schedule   → game results
                                                                    │
                                                          scraper/scrape.py
                                                                    │
                                                          docs/data.json  (committed by GitHub Actions)
                                                                    │
                                                          docs/index.html  (served by GitHub Pages)
```

1. **`scraper/scrape.py`** fetches data for all 22 teams and writes `docs/data.json`.
2. **GitHub Actions** (`.github/workflows/update.yml`) runs the scraper daily at 6 AM UTC and commits any changes.
3. **`docs/index.html`** reads `data.json` and renders the grid — no server needed.

## Running the scraper locally

```bash
# from the repo root
python scraper/scrape.py
```

Then preview the page:

```bash
python -m http.server 8080 --directory docs
# open http://localhost:8080
```

## Enabling GitHub Pages

In your repo on GitHub:

1. **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` · Folder: `/docs`
4. Save — your page will be live at `https://robwinship.github.io/sarnia-brigade-stats/`

## Score parsing note

Score parsing uses regex patterns matched against the MBSportsWeb HTML.
The 2026 season begins **April 25, 2026**.  If any result or score looks wrong
once real games are played, open `scraper/scrape.py` and adjust the
`RESULT_RE` / `SCORE_RE` constants near the top of the file.
