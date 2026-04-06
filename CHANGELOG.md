# Changelog

All notable changes to gitmanager are documented here.

---

## [2.1] — 2026-04-06

### Added
- README generation via Ollama with side-by-side comparison modal (existing vs generated)
- Real-time search filter in the sidebar project list
- `git init` and `git_new_branch` functions (were referenced in routes but missing from `server.py`)

### Changed
- Full UI translation from Portuguese to English (labels, modals, toasts, placeholders)
- Project type and status dropdown values updated to English (`in development`, `production`, `archived`, etc.)

### Fixed
- `NameError` on `/api/init` and `/api/new_branch` routes caused by missing function definitions

---

## [2.0]

### Added
- Ollama integration for commit message suggestions
- Dynamic model selector (auto-loaded from local Ollama installation)
- Optional context field in commit area to guide LLM suggestions
- `git diff --cached` fallback to unstaged diff when no staged changes exist

---

## [1.1]

### Added
- Edit project modal — update description, stack, type, status, remote, path
- Remove project from registry (folder is never deleted)
- Auto-detect project info from `.git` folder (remote, stack, type) via Load button
- `git pull` support
- Branch creation and checkout UI

---

## [1.0]

### Added
- Python stdlib HTTP server, zero external dependencies
- Web interface — dark theme, IBM Plex Mono, responsive two-panel layout
- Project registry via `projects.json` (gitignored — local paths stay private)
- Projects grouped by type in sidebar (contracts, frontend, automation, tools, sandbox)
- Git status with color-coded file states (modified, added, deleted, untracked)
- Diff viewer — summary and full
- Commit history (last 10)
- Commit with `git add .` + message input
- Push with mandatory confirmation modal
- Open project in VS Code
- Add new project via form with optional `git init`
- Toast notifications for all actions
