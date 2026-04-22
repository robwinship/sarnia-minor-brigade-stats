# Changelog
## v1.23 - 2026-04-22 17:13:56
- Modified the umpire upcoming issues to only show 1 week out conflicts

## v1.22 - 2026-04-22 17:08:25
- Backup created

## v1.22 - 2026-04-22
- Changed Umpire Issues: Upcoming conflicts now only include games within the next 7 days (inclusive of today), excluding farther-future conflicts from upcoming counts/details.

## v1.21 - 2026-04-18 10:46:18
- Backup created

## v1.20 - 2026-04-01 18:52:27
- Backup created

## v1.19 - 2026-03-29 21:28:34
- Backup created

## v1.18 - 2026-03-29 21:22:18
- Backup created

## v1.17 - 2026-03-29 13:40:51
- Backup created

## v1.16 - 2026-03-28 20:15:33
- Backup created

## v1.15 - 2026-03-28 18:45:52
- Backup created

## v1.14 - 2026-03-28 18:08:39
- Backup created

## v1.13 - 2026-03-28 17:55:51
- Backup created

## v1.12 - 2026-03-27 23:35:25
- Backup created

## v1.11 - 2026-03-27 22:03:56
- Backup created

## v1.10 - 2026-03-27 12:18:12
- Backup created

## v1.09 - 2026-03-25 21:51:59
- Backup created

## v1.08 - 2026-03-25 21:05:05
- Backup created
- Removed 13U River League from tracked teams so all tabs and aggregate calculations exclude the retired team

## v1.07 - 2026-03-22 09:24:40
- Backup created

## v1.06 - 2026-03-21 19:25:46
- Backup created

## v1.051 - 2026-03-21
- Updated Budget Model and Diamond Summary tabs to match Season Stats presentation style with category-grouped blocks
- Aligned Budget Model team ordering to match Season Stats ordering
- Reworked Diamond Summary team view to group by category in the same order as Season Stats while preserving grouped-by-diamond mode
- Updated Budget Model table columns by replacing Home Games/Practices with placeholder future-metric columns

## v1.05 - 2026-03-21
- Added Budget Model tab with per-event diamond rental costing (day/evening hourly rates for two diamond tiers)
- Implemented day/evening rate split for diamond rental: 7 AM–7:30 PM (day) and 8 PM–midnight (evening) with 2-hour booking defaults
- Configured diamond rate tier A (Errol Russell Park, Blackwell Park): $38.18 day / $55.12 evening per hour
- Configured diamond rate tier B (Clearwater 1/2/3, Germain 1/2/3/4/5, Tecumseh Park): $34.13 day / $51.07 evening per hour
- Added umpire costing by age tier: 8U/9U ($46), 10U/11U ($51), 12U/13U ($56), 14U+ ($66) per umpire—2 umpires per home game on home diamonds
- Added insurance costing at $7.60 per person ($7.52 + 1.13% tax) applied to active team roster counts
- Integrated roster parsing to capture players and adult role counts (Head Coach, Assistant Coach, Coach, Manager) per team
- Budget model filters apply costs only to home games and practices on approved Sarnia home diamonds; away games and non-configured locations default to $0
- Date-range filtering available for budget cost projections within season windows

## v1.04 - 2026-03-20 20:57:52
- Backup created

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
