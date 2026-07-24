# gitmanager

Local Git repository manager with a web interface — no external dependencies.

## What it does

A centralized dashboard to manage multiple Git projects from a single interface. Built with Python's built-in HTTP server and plain HTML/JS, requiring nothing beyond a standard Python installation.

Includes an **Ecosystem Status View** that shows the git health of all registered projects at a glance, and LLM-powered features (commit suggestions, README generation) backed by [pandagent](https://github.com/pantalipe/pandagent)'s shared Ollama client.

## Features

- **Ecosystem view** — card grid with git health semaphore for all projects, grouped by layer
- Project list organized by type (contracts, frontend, automation, tools)
- Git status with color-coded file states
- Diff viewer — summary and full
- Commit history (last 10)
- Branch management — create and checkout
- Commit message suggestion via Ollama — context-aware, uses project metadata as scope
- README generation via Ollama with side-by-side comparison modal
- Pull
- Push with mandatory confirmation modal
- Open project in VS Code
- Add new project via form (with optional `git init`)
- Edit project metadata (description, stack, type, status, remote)
- Remove project from registry (folder is never deleted)
- Persistent project registry via `projects.json`

## Structure

```
gitmanager/
├── server.py        # HTTP server + git routes + LLM integration
├── projects.json    # project registry
└── static/
    └── index.html   # web interface (Projects + Ecosystem tabs)
```

## Usage

```bash
python server.py
```

Open `http://localhost:8765` in your browser.

No `pip install` required.

## LLM integration

LLM features (commit suggestions, README generation, model listing) are handled by
[pandagent](https://github.com/pantalipe/pandagent), imported as an installable package.
Install it once with `pip install -e ../pandagent` and the integration is automatic.
If pandagent is not installed, the server falls back to direct OpenAI-compatible
urllib calls against `http://127.0.0.1:8081` (overridable via `LLM_BASE_URL`) — no
configuration needed.

Commit message suggestions are context-aware: the project's `description`, `objective`
and `stack` from `projects.json` are injected into the prompt so the model generates
messages scoped to the actual project (e.g. `feat(gitmanager): ...` instead of
`feat(server.py): ...`).

## projects.json

Each project entry supports:

```json
{
  "path": "C:/Users/panta/my-project",
  "description": "Short description",
  "objective": "What problem it solves",
  "status": "in development",
  "stack": ["python", "javascript"],
  "type": "tool",
  "git_remote": "https://github.com/user/repo.git",
  "require_confirmation": ["git push", "git reset"]
}
```

The `description`, `objective` and `stack` fields are used by the LLM when generating
commit messages and READMEs.

## Roadmap

| Version | Status | Features |
|---------|--------|----------|
| v1.0 | ✅ done | Base manager — status, diff, commit, push, VS Code integration |
| v1.1 | ✅ done | Edit/remove projects, git remote config via UI |
| v2.0 | ✅ done | LLM integration via Ollama — commit message suggestions, dynamic model selector |
| v2.1 | ✅ done | README generation via Ollama with side-by-side comparison modal |
| v2.2 | ✅ done | PandaClient integration, ecosystem status view, project-aware commit context |
| v3.0 | 🔜 planned | pandagent full integration — delegate LLM tasks to the agent for richer context-aware suggestions |
