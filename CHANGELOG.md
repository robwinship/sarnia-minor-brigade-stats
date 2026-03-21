# Changelog
## v1.025 - 2026-03-20
- Added date-range filter controls to Diamond Summary tab (Start Date, End Date, Apply Range, Full Season)
- Made home-game and practice-event counts expandable/clickable to show event date lists for invoice reconciliation
- Removed First Date and Last Date columns from Diamond Summary table—date filtering now handled by range controls
- Diamond Summary now tracks individual event objects to enable drill-down detail views

## v1.024 - 2026-03-20
- Updated Diamond Summary to use the official home venue list provided in the CSV (Name column)
- Added venue-name normalization for reliable matching across case/spacing variations
- Home-diamond statistics now exclude home-designated games played at non-listed away centers

## v1.023 - 2026-03-20
- Added Diamond Summary tab with Team and Diamond filters for Sarnia Brigade teams
- Changed home diamond tracking to use explicit schedule home-game flags, then map to event locations by team/date
- Added second Diamond Summary view mode grouped by Diamond (in addition to grouped by Team)

## v1.022 - 2026-03-20
- Fixed tournament detection in scraper: events with a /Tournaments/ URL in their ICS DESCRIPTION are now classified as type "tournament" regardless of summary text
- Fixed frontend tournament tab to match on type="tournament" in addition to the "tournament" keyword, so events like "Great Lakes World Series" and "PBLO 16u Championship" appear correctly
- Regenerated data.json with corrected tournament types

## v1.021 - 2026-03-20
- Added Tournaments tab to the season summary page
- Tournaments are derived from existing event data (events with "Tournament" in the name)
- Team filter dropdown auto-populates with only teams that have tournament entries
- Table shows dates, tournament name, team, and location, sorted chronologically

## v1.02 - 2026-03-18 21:14:00
- Backup created

## v1.01 - 2026-03-18 21:06:09
- Backup created


## v1.00 - 2026-03-18
- Initial version: season stats grid with GP, W/L/T, RF/RA, run differential, win percentage
- Home and Away game counts replacing the Game/Exh column
- Practice and Pitch Indoor Sports event tracking
- Expandable date lists for practice and Pitch events
- Date range filtering with full season reset
- Brigade logo in page header
- GitHub Actions workflow for automated data refresh
