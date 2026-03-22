# gitmanager

Local Git repository manager with a web interface — no external dependencies.

## What it does

A centralized dashboard to manage multiple Git projects from a single interface. Built with Python's built-in HTTP server and plain HTML/JS, requiring nothing beyond a standard Python installation.

## Features

- Project list organized by type (contracts, frontend, automation, tools)
- Git status with color-coded file states
- Diff viewer — summary and full
- Commit history (last 10)
- Branch management — create and checkout
- Commit with optional change description field
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
├── server.py        # HTTP server + git routes
├── projects.json    # project registry
└── static/
    └── index.html   # web interface
```

## Usage

```bash
python server.py
```

Open `http://localhost:8765` in your browser.

No `pip install` required.

## projects.json

Each project entry supports:

```json
{
  "path": "C:/Users/panta/my-project",
  "description": "Short description",
  "objective": "What problem it solves (used by LLM in future versions)",
  "status": "em desenvolvimento",
  "stack": ["python", "javascript"],
  "type": "tool",
  "git_remote": "https://github.com/user/repo.git",
  "require_confirmation": ["git push", "git reset"]
}
```

## Roadmap

| Version | Status | Features |
|---------|--------|----------|
| v1.0 | ✅ done | Base manager — status, diff, commit, push, VS Code integration |
| v1.1 | ✅ done | Edit/remove projects, git remote config via UI |
| v2.0 | 🔜 planned | LLM integration via Ollama — README generation, commit message suggestions |
| v2.1 | 🔜 planned | Edit LLM output before saving, choose model from UI |
