# Changelog

All notable changes to gitmanager are documented here.

---

## [Unreleased]

---

## [2.3] — 2026-05-10

### Changed
- LLM fallback paths in `server.py` (used when pandagent is unavailable) migrated from
  Ollama's native API to the OpenAI-compatible `/v1/chat/completions` endpoint
- `LLM_BASE_URL = "http://127.0.0.1:8080"` constant added
- `get_ollama_models()` fallback: `/api/tags` → `/v1/models`, parses `data[].id`
  instead of `models[].name`
- `generate_readme()` and `suggest_commit_message()` fallbacks: `/api/generate` →
  `/v1/chat/completions` via new `_llm_chat()` helper; response parsed from
  `choices[0].message.content`
- All "Ollama" strings in fallback error messages updated to "LLM server"

---

## [2.2] — 2026-05-04

### Changed
- `server.py` migrated from `sys.path` import to `from pandagent import PandaClient`
  — requires `pip install -e ../pandagent` instead of path manipulation

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
