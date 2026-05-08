# System-level changes made by Claude Code — 2026-05-07

## Software installed

- **tectonic 0.16.9** — a Rust-based LaTeX engine
  - Installed via: `brew install tectonic`
  - Location: `/opt/homebrew/Cellar/tectonic/0.16.9` (10 files, 16.5MB)
  - To uninstall: `brew uninstall tectonic`

## Software installation attempted but failed (no effect)

- **basictex** (MacTeX BasicTeX) — `brew install --cask basictex` failed because the installer requires sudo. No files were written.
- **tlmgr package install** (`environ`, `lineno`, `natbib`, `booktabs`, `microtype`, `hyperref`) — failed due to write permissions on `/usr/local/texlive/`. No packages were installed.

## No other system-level changes

- No environment variables modified
- No shell profiles edited
- No git config changed
- No LaunchAgents/daemons created
- No cron jobs added
