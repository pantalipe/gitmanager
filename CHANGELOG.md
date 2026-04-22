# Changelog

All notable changes to gitmanager are documented here.

---

## [Unreleased]

### Added
- **Ecosystem Status View** — new "⬡ Ecosystem" tab in the header with a card grid
  showing git health for all projects at a glance
  - Per-project semaphore: `clean` (green), `dirty` (yellow), `no_git` (grey), `no_path` (red)
  - Cards grouped by ecosystem layer (Dev Tooling / Content Pipeline / Web3 Product)
  - Each card shows: branch, changed file count, commits ahead of remote, stack tags,
    last commit time and message
  - Clicking any card navigates directly to that project in the Projects view
  - Stats bar with total counts per health state
  - `GET /api/ecosystem_status` endpoint powering the view
- **PandaClient integration** — `server.py` now imports `panda_client.py` from
  `../pandagent` as the single point of contact with Ollama
  - `suggest_commit_message()` delegates to `_panda.commit_message()`
  - `generate_readme()` delegates to `_panda.generate_readme()`
  - `get_ollama_models()` delegates to `_panda.available_models()`
  - Graceful fallback to direct Ollama urllib calls if pandagent is not found;
    startup log reports `PandaClient: loaded` or `not found (fallback mode)`
- **Project context in commit prompts** — `suggest_commit_message()` now accepts
  `project_name` and `project_cfg` and injects project metadata (name, description,
  purpose, tech stack) as structured background context into the LLM prompt
- `_build_project_context()` — builds bracket-notation context block from
  `projects.json` metadata to prevent verbatim reproduction in model output
- `_clean_commit()` — post-processing cleaner that extracts the first valid
  conventional commit line, strips leaked context, issue references (`#`) and
  markdown artifacts
- `_clean_markdown_fences()` — strips ` ```markdown ` fences from README output

### Changed
- `suggest_commit_message()` passes `project_name` to `_panda.commit_message()`
  for explicit scope enforcement (model instructed to use project name as scope)
- `_COMMIT_LEAK_MARKERS` in fallback `_clean_commit()` expanded to include
  `status:`, `stack:`, `objective:`, `description:`, sentence-continuation
  patterns and ` #` issue references
- Fallback `suggest_commit_message()` prompt updated to match panda_client format:
  `### git status`, `### git diff`, `### project context` sections

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
