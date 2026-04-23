# Sarnia Brigade — Season Stats

Per-team season summary for the [Sarnia Brigade Minor Baseball Association](https://www.sarniabrigade.ca).

## Live Page

> **[robwinship.github.io/sarnia-minor-brigade-stats](https://robwinship.github.io/sarnia-minor-brigade-stats)**

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

The page also includes:

1. A selectable **start date** and **end date** so you can view a custom summary range instead of only full-season totals.
2. A **Pitch Indoor Sports Tracker** that lists all matching team events in the selected range.
3. Expandable team columns for **Game/Exh**, **Practice**, and **Pitch** that show the event dates when clicked.
4. An **Umpire Issues** tab with:
       - **Games Missed**: games with fewer than two assigned umpires.
       - **Doubleheader Umpire Mismatch**: same-team/same-date doubleheaders where assigned umpire pairs are not consistent between games.

## How it works

```
sarniabrigade.ca
       │
       ├── /webcal.ashx?IDs=<teamId>    ← iCalendar feed  → dated team events / practices / locations
       └── /Teams/<id>/Schedule/        ← HTML schedule   → dated game results
public Google Sheet CSV
       │
       └── Team / Uniform $ / Equipment $
                                                                    │
                                                          scraper/scrape.py
                                                                    │
                                                          docs/data.json  (committed by GitHub Actions)
                                                                    │
                                                          docs/index.html  (date-range filtering + Pitch tracker)
```

1. **`scraper/scrape.py`** fetches data for all 22 teams, merges public budget metrics by exact team name, and writes `docs/data.json`.
2. **GitHub Actions** (`.github/workflows/update.yml`) runs only when you trigger it manually from the Actions tab and commits any changes.
3. **`docs/index.html`** reads `data.json` and renders the grid — no server needed.

## Update frequency

The page updates only when you choose to run the workflow.

Manual update flow:

1. Open **Actions** in GitHub.
2. Open **Update Season Stats**.
3. Click **Run workflow**.
4. Wait for the job to finish.
5. Refresh the live page.

The page also includes:

1. A **Get Update** button that reloads the published `data.json`.
2. A **Run Update** button that opens the GitHub Actions workflow page.

Because the site is hosted on GitHub Pages, the browser cannot run the Python scraper directly.

## Running the scraper locally

```bash
# from the repo root
python scraper/scrape.py
```

For Officials/umpire scraping, set credentials first:

```powershell
$env:CP_USERNAME="your_username"
$env:CP_PASSWORD="your_password"
python scraper/scrape.py
```

If credentials are missing or Officials data cannot be collected, umpire metrics default to `0` and the page will show umpire data as unavailable.

Budget Model metrics are also imported during scraping from a public Google Sheets CSV export. The default CSV source is the published `gid=0` sheet tab, and rows are matched by exact team name.

Expected CSV headers:

```text
Team,Uniform $,Equipment $
```

If you move the data to another published sheet or tab, override the default URL before running the scraper:

```powershell
$env:PUBLIC_BUDGET_METRICS_CSV_URL="https://docs.google.com/spreadsheets/d/<spreadsheet_id>/export?format=csv&gid=<gid>"
python scraper/scrape.py
```

GitHub Actions credentials (for workflow updates):

1. Open **Settings → Secrets and variables → Actions** in the repository.
2. Create repository secret **CP_USERNAME** with your CP username.
3. Create repository secret **CP_PASSWORD** with your CP password.
4. Run the workflow from **Actions → Update Season Stats**.

The workflow passes these secrets as environment variables to the scraper. If secrets are not set, the update still runs and marks umpire data unavailable.

Playwright setup (first time):

```bash
pip install -r scraper/requirements.txt
python -m playwright install chromium
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
4. Save — your page will be live at `https://robwinship.github.io/sarnia-minor-brigade-stats/`

## Score parsing note

Score parsing uses regex patterns matched against the MBSportsWeb HTML.
The 2026 season begins **April 25, 2026**.  If any result or score looks wrong
once real games are played, open `scraper/scrape.py` and adjust the
`RESULT_RE` / `SCORE_RE` constants near the top of the file.
