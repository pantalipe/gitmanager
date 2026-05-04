"""
server.py — Git Manager local
Servidor HTTP embutido do Python, zero dependências externas.

Uso:
    python server.py
    Abra: http://localhost:8765
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ── PandaClient (shared LLM module) ─────────────────────────────────────────
try:
    from pandagent import PandaClient
    _panda = PandaClient()
    _PANDA_AVAILABLE = True
except ImportError:
    _PANDA_AVAILABLE = False

PROJECTS_FILE = Path(__file__).parent / "projects.json"
TODOS_DIR     = Path(__file__).parent / "todos"
PORT          = 8765
STATIC_DIR    = Path(__file__).parent / "static"


# ─────────────────────────────────────────────
# OUTPUT CLEANERS (fallback — mirrors panda_client logic)
# ─────────────────────────────────────────────
def _clean_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:markdown)?\s*\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text)
    text = re.sub(r"^markdown\s*\n", "", text, flags=re.IGNORECASE)
    return text.strip()


def _clean_commit(raw: str) -> str:
    if not raw:
        return raw
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    if not lines:
        return raw
    conventional_types = ("feat", "fix", "refactor", "docs", "chore", "test", "style", "perf", "build", "ci")
    candidate = lines[0]
    for line in lines:
        if any(line.lower().startswith(t) for t in conventional_types):
            candidate = line
            break
    candidate = candidate.strip("`*\"'")
    leak_markers = [
        "developer notes:", "developer context:", "project context:",
        "generate the commit message", "git status:", "git diff:",
        "reply only", "status:", "stack:", "objective:", "description:",
        ". prepared to", ". status:", ". stack:", " #",
    ]
    lower = candidate.lower()
    cut_at = len(candidate)
    for marker in leak_markers:
        idx = lower.find(marker)
        if idx != -1 and idx < cut_at:
            cut_at = idx
    candidate = candidate[:cut_at].strip()
    if len(candidate) > 72:
        candidate = candidate[:72].rsplit(" ", 1)[0]
    return candidate.rstrip(".,;:").strip()


def _build_project_context(project_name: str, project_cfg: dict) -> str:
    parts = [f"[project: {project_name}]"]
    description = project_cfg.get("description", "").strip()
    if description:
        parts.append(f"[what it does: {description}]")
    objective = project_cfg.get("objective", "").strip()
    if objective:
        parts.append(f"[purpose: {objective}]")
    stack = project_cfg.get("stack", [])
    if stack:
        parts.append(f"[tech: {', '.join(stack)}]")
    return "\n".join(parts)


# ─────────────────────────────────────────────
# CARREGA PROJETOS
# ─────────────────────────────────────────────
def load_projects() -> dict:
    if not PROJECTS_FILE.exists():
        return {}
    with open(PROJECTS_FILE, encoding="utf-8") as f:
        return json.load(f).get("projects", {})


# ─────────────────────────────────────────────
# GIT HELPERS
# ─────────────────────────────────────────────
def run_git(path: str, args: list[str]) -> dict:
    if not Path(path).exists():
        return {"ok": False, "output": f"Pasta nao encontrada: {path}", "code": -1}
    try:
        result = subprocess.run(
            ["git"] + args, cwd=path, capture_output=True, text=True,
            timeout=30, encoding="utf-8", errors="replace",
        )
        output = result.stdout or result.stderr or "(no output)"
        return {"ok": result.returncode == 0, "output": output.strip(), "code": result.returncode}
    except FileNotFoundError:
        return {"ok": False, "output": "Git nao encontrado.", "code": -1}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "Timeout.", "code": -1}
    except Exception as e:
        return {"ok": False, "output": str(e), "code": -1}


def git_status(path: str) -> dict:
    return run_git(path, ["status", "--short", "--branch"])

def git_diff(path: str) -> dict:
    return run_git(path, ["diff", "--stat"])

def git_diff_full(path: str) -> dict:
    return run_git(path, ["diff"])

def git_log(path: str) -> dict:
    return run_git(path, ["log", "--oneline", "-10"])

def git_branches(path: str) -> dict:
    return run_git(path, ["branch", "-a"])

def git_init(path: str) -> dict:
    return run_git(path, ["init"])

def git_new_branch(path: str, branch: str) -> dict:
    return run_git(path, ["checkout", "-b", branch])

def git_commit(path: str, message: str) -> dict:
    run_git(path, ["add", "."])
    return run_git(path, ["commit", "-m", message])

def git_diff_staged(path: str) -> dict:
    staged = run_git(path, ["diff", "--cached"])
    if staged["ok"] and staged["output"] and staged["output"] != "(no output)":
        return staged
    return run_git(path, ["diff"])

def get_ollama_models() -> dict:
    if _PANDA_AVAILABLE:
        models = _panda.available_models()
        if models:
            return {"ok": True, "models": models}
        return {"ok": False, "models": [], "output": "Ollama unavailable."}
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "models": [m["name"] for m in result.get("models", [])]}
    except Exception as e:
        return {"ok": False, "models": [], "output": f"Ollama unavailable: {e}"}


def get_bench_results() -> dict:
    """
    Reads the most recent bench JSON from ollama-bench/results/.
    Returns a summarized view: per model -> per category -> avg metrics.
    """
    bench_dir = Path(__file__).parent.parent / "ollama-bench" / "results"
    if not bench_dir.exists():
        return {"ok": False, "output": "ollama-bench/results not found", "data": {}}

    json_files = sorted(bench_dir.glob("*.json"), reverse=True)
    json_files = [f for f in json_files if f.suffix == ".json" and f.stem != ".gitkeep"]
    if not json_files:
        return {"ok": False, "output": "No bench results found. Run bench.py first.", "data": {}}

    try:
        with open(json_files[0], encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        return {"ok": False, "output": str(e), "data": {}}

    aggregated = {}
    for entry in raw.get("results", []):
        model    = entry.get("model", "unknown")
        category = entry.get("category", "other")
        summary  = entry.get("summary", {})
        if not summary:
            continue
        aggregated.setdefault(model, {}).setdefault(category, []).append(summary)

    def avg(vals):
        v = [x for x in vals if x is not None]
        return round(sum(v) / len(v), 2) if v else None

    models_summary = {}
    for model, cats in aggregated.items():
        models_summary[model] = {}
        for cat, summaries in cats.items():
            models_summary[model][cat] = {
                "avg_tokens_per_second":     avg([s.get("avg_tokens_per_second")     for s in summaries]),
                "avg_time_to_first_token_s": avg([s.get("avg_time_to_first_token_s") for s in summaries]),
                "avg_total_duration_s":      avg([s.get("avg_total_duration_s")      for s in summaries]),
                "consistency_score":         avg([s.get("consistency_score")         for s in summaries]),
                "prompts_run":               len(summaries),
            }

    return {
        "ok":        True,
        "timestamp": raw.get("timestamp", ""),
        "system":    raw.get("system", {}),
        "models":    list(raw.get("models", [])),
        "data":      models_summary,
    }


# ─────────────────────────────────────────────
# HEALTH SCORING HELPERS
# ─────────────────────────────────────────────

def _get_commit_days(path: str) -> float | None:
    """Returns days since the last commit, or None if no commits or no git."""
    result = run_git(path, ["log", "-1", "--format=%ct"])
    if not result["ok"]:
        return None
    raw = result["output"].strip()
    if not raw or raw == "(no output)":
        return None
    try:
        ts = int(raw)
        return (time.time() - ts) / 86400.0
    except ValueError:
        return None


def _read_todos(project_name: str) -> list[dict]:
    """
    Reads todos from gitmanager/todos/{project_name}.json.
    Centralised in gitmanager — never touches the project directories.
    Returns [] if file absent or malformed.
    """
    todo_path = TODOS_DIR / f"{project_name}.json"
    if not todo_path.exists():
        return []
    try:
        data = json.loads(todo_path.read_text(encoding="utf-8"))
        todos = data.get("todos", [])
        normalised = []
        for item in todos:
            if isinstance(item, str):
                normalised.append({"text": item, "done": False})
            elif isinstance(item, dict):
                normalised.append({
                    "text": str(item.get("text", "")),
                    "done": bool(item.get("done", False)),
                })
        return normalised
    except Exception:
        return []


def _save_todos(project_name: str, todos: list[dict]) -> dict:
    """Writes todos to gitmanager/todos/{project_name}.json."""
    TODOS_DIR.mkdir(exist_ok=True)
    todo_path = TODOS_DIR / f"{project_name}.json"
    try:
        todo_path.write_text(
            json.dumps({"todos": todos}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"ok": True, "output": f"todos/{project_name}.json saved."}
    except Exception as e:
        return {"ok": False, "output": str(e)}


def _compute_score(days_since_commit: float | None, open_todos: int, health: str) -> str:
    """
    Traffic-light health score for a project.

    RED    — path/git missing, or stale > 30 days, or 5+ open todos
    YELLOW — dirty working tree, or stale 7-30 days, or 1-4 open todos
    GREEN  — clean, committed < 7 days ago, 0 open todos
    """
    if health in ("no_path", "no_git"):
        return "red"
    if days_since_commit is not None and days_since_commit > 30:
        return "red"
    if open_todos >= 5:
        return "red"
    if health == "dirty":
        return "yellow"
    if days_since_commit is not None and days_since_commit > 7:
        return "yellow"
    if open_todos >= 1:
        return "yellow"
    return "green"


def ecosystem_status() -> dict:
    projects = load_projects()
    result = {}
    for name, cfg in projects.items():
        path = cfg.get("path", "")
        entry = {
            "name": name, "description": cfg.get("description", ""),
            "type": cfg.get("type", "other"), "stack": cfg.get("stack", []),
            "path_exists": False, "branch": None, "changed_files": 0,
            "last_commit": None, "last_message": None, "ahead": None,
            "health": "no_path",
            "days_since_commit": None,
            "todos": [],
            "todo_count": 0,
            "open_todo_count": 0,
            "score": "red",
        }
        if not path or not Path(path).exists():
            result[name] = entry
            continue
        entry["path_exists"] = True
        if not (Path(path) / ".git").exists():
            entry["health"] = "no_git"
            todos = _read_todos(name)
            open_todos = sum(1 for t in todos if not t["done"])
            entry["todos"] = todos
            entry["todo_count"] = len(todos)
            entry["open_todo_count"] = open_todos
            entry["score"] = _compute_score(None, open_todos, "no_git")
            result[name] = entry
            continue
        status_r = run_git(path, ["status", "--short", "--branch"])
        if status_r["ok"]:
            lines = status_r["output"].split("\n")
            branch_line = lines[0] if lines else ""
            m = re.match(r"## ([^.]+)", branch_line)
            if m:
                entry["branch"] = m.group(1).strip()
            am = re.search(r"\[ahead (\d+)\]", branch_line)
            if am:
                entry["ahead"] = int(am.group(1))
            entry["changed_files"] = len([l for l in lines[1:] if l.strip()])
        log_r = run_git(path, ["log", "-1", "--format=%cr|||%s"])
        if log_r["ok"] and log_r["output"] and log_r["output"] != "(no output)":
            parts = log_r["output"].split("|||", 1)
            entry["last_commit"]  = parts[0].strip() if parts else None
            entry["last_message"] = parts[1].strip() if len(parts) > 1 else None
        entry["health"] = "dirty" if entry["changed_files"] > 0 else "clean"

        days = _get_commit_days(path)
        entry["days_since_commit"] = round(days, 1) if days is not None else None

        todos = _read_todos(name)
        open_todos = sum(1 for t in todos if not t["done"])
        entry["todos"] = todos
        entry["todo_count"] = len(todos)
        entry["open_todo_count"] = open_todos

        entry["score"] = _compute_score(days, open_todos, entry["health"])

        result[name] = entry
    return {"ok": True, "projects": result}


def scan_project_structure(path: str) -> str:
    root = Path(path)
    ignore = {'.git', 'node_modules', '__pycache__', '.next', 'dist', 'build', '.env', 'venv', '.venv'}
    lines = []
    for item in sorted(root.rglob('*')):
        if any(p in item.parts for p in ignore):
            continue
        rel = item.relative_to(root)
        if len(rel.parts) - 1 > 3:
            continue
        prefix = '  ' * (len(rel.parts) - 1)
        lines.append(f"{prefix}[{rel.name}/]" if item.is_dir() else f"{prefix}{rel.name}")
    extras = []
    for fname in ['package.json', 'requirements.txt', 'pyproject.toml', 'Cargo.toml']:
        fpath = root / fname
        if fpath.exists():
            try:
                extras.append(f"\n--- {fname} ---\n{fpath.read_text(encoding='utf-8', errors='replace')[:800]}")
            except Exception:
                pass
    return '\n'.join(lines) + ''.join(extras)


def get_existing_readme(path: str) -> str:
    readme = Path(path) / 'README.md'
    if readme.exists():
        try:
            return readme.read_text(encoding='utf-8', errors='replace')
        except Exception:
            pass
    return ''


def save_readme(path: str, content: str) -> dict:
    try:
        (Path(path) / 'README.md').write_text(content, encoding='utf-8')
        return {'ok': True, 'output': 'README.md saved.'}
    except Exception as e:
        return {'ok': False, 'output': str(e)}


def generate_readme(path: str, project_cfg: dict, model: str = "phi3") -> dict:
    structure = scan_project_structure(path)
    if _PANDA_AVAILABLE:
        _panda.text_model = model
        return _panda.generate_readme(
            project_name=project_cfg.get("name", Path(path).name),
            description=project_cfg.get("description", ""),
            objective=project_cfg.get("objective", ""),
            stack=project_cfg.get("stack", []),
            status=project_cfg.get("status", ""),
            file_structure=structure,
        )
    name = project_cfg.get("name", Path(path).name)
    prompt = (
        "You are a technical writer. Generate a clean README.md in English.\n"
        "Output raw markdown only. Do NOT use ```markdown fences. Start with # ProjectName.\n\n"
        f"Project name: {name}\nDescription: {project_cfg.get('description','')}\n"
        f"Objective: {project_cfg.get('objective','')}\nStack: {', '.join(project_cfg.get('stack',[]))}\n"
        f"Status: {project_cfg.get('status','')}\n\nFile structure:\n{structure}"
    )
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=None) as resp:
            content = _clean_markdown_fences(json.loads(resp.read().decode("utf-8")).get("response", "").strip())
            if not content:
                return {"ok": False, "output": "Ollama returned empty response."}
            return {"ok": True, "output": content}
    except Exception as e:
        return {"ok": False, "output": f"Ollama error: {e}"}


def suggest_commit_message(
    path: str,
    user_context: str = "",
    model: str = "phi3",
    project_name: str = "",
    project_cfg: dict = None,
) -> dict:
    diff        = git_diff_staged(path)
    status      = git_status(path)
    diff_text   = diff.get("output", "").strip()
    status_text = status.get("output", "").strip()

    context_parts = []
    if project_name and project_cfg:
        context_parts.append(_build_project_context(project_name, project_cfg))
    if user_context.strip():
        context_parts.append(f"Developer notes: {user_context.strip()}")
    enriched_context = "\n\n".join(context_parts)

    if _PANDA_AVAILABLE:
        _panda.text_model = model
        return _panda.commit_message(
            diff=diff_text,
            status=status_text,
            extra_context=enriched_context,
            project_name=project_name,
        )

    scope_hint = f"Use '{project_name}' as the scope. " if project_name else ""
    context_block = f"\n### project context\n{enriched_context}" if enriched_context else ""
    prompt = (
        "You are a git commit message generator.\n"
        f"{scope_hint}Output ONE line only: <type>(<scope>): <description>\n"
        "Valid types: feat, fix, refactor, docs, chore, test, style, perf\n"
        "No issue references (#). Write NOTHING else. Stop after the first line.\n\n"
        f"### git status\n{status_text}\n\n"
        f"### git diff\n{diff_text[:3000]}"
        f"{context_block}\n\n"
        "Commit message:"
    )
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False,
                          "options": {"num_predict": 80}}).encode("utf-8")
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=None) as resp:
            message = _clean_commit(json.loads(resp.read().decode("utf-8")).get("response", "").strip())
            if not message:
                return {"ok": False, "output": "Ollama returned empty response."}
            return {"ok": True, "output": message}
    except Exception as e:
        return {"ok": False, "output": f"Ollama error: {e}"}


def git_push(path: str, remote: str = "origin", branch: str = "") -> dict:
    args = ["push", remote]
    if branch:
        args.append(branch)
    return run_git(path, args)

def git_pull(path: str) -> dict:
    return run_git(path, ["pull"])

def git_checkout(path: str, branch: str) -> dict:
    return run_git(path, ["checkout", branch])

def open_vscode(path: str) -> dict:
    if not Path(path).exists():
        return {"ok": False, "output": f"Pasta nao encontrada: {path}"}
    try:
        subprocess.Popen(["code", path], shell=True)
        return {"ok": True, "output": f"Abrindo no VS Code: {path}"}
    except Exception as e:
        return {"ok": False, "output": str(e)}


def detect_project_from_path(path: str) -> dict:
    root = Path(path)
    if not root.exists():
        return {"ok": False, "output": f"Pasta nao encontrada: {path}"}
    if not (root / ".git").exists():
        return {"ok": False, "output": "Nenhum repositorio .git encontrado."}
    name = root.name
    remote = run_git(path, ["remote", "get-url", "origin"])
    git_remote = remote["output"] if remote["ok"] else ""
    stack_hints = {
        "package.json": "javascript", "requirements.txt": "python",
        "pyproject.toml": "python", "Cargo.toml": "rust",
        "go.mod": "go", "pom.xml": "java", "*.sol": "solidity",
    }
    stack = []
    for fname, lang in stack_hints.items():
        if fname.startswith("*"):
            if any(root.glob(f"**/*{fname[1:]}")):
                stack.append(lang)
        elif (root / fname).exists():
            stack.append(lang)
    project_type = "other"
    if any(root.glob("**/*.sol")):
        project_type = "contract"
    elif (root / "package.json").exists():
        try:
            pkg  = json.loads((root / "package.json").read_text(encoding="utf-8", errors="replace"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if any(k in deps for k in ["next", "react", "vue", "svelte"]):
                project_type = "frontend"
        except Exception:
            pass
    elif any(root.glob("**/*.py")):
        project_type = "tool"
    return {"ok": True, "name": name, "path": str(root),
            "git_remote": git_remote.strip(), "stack": stack, "type": project_type}


def save_project(name: str, cfg: dict) -> dict:
    try:
        data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8")) if PROJECTS_FILE.exists() else {"projects": {}, "settings": {}}
        data["projects"][name] = cfg
        with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"ok": True, "output": f"Projeto '{name}' salvo."}
    except Exception as e:
        return {"ok": False, "output": str(e)}


def remove_project(name: str) -> dict:
    try:
        if not PROJECTS_FILE.exists():
            return {"ok": False, "output": "projects.json nao encontrado"}
        data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
        if name not in data.get("projects", {}):
            return {"ok": False, "output": f"Projeto '{name}' nao encontrado"}
        del data["projects"][name]
        with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"ok": True, "output": f"Projeto '{name}' removido."}
    except Exception as e:
        return {"ok": False, "output": str(e)}


# ─────────────────────────────────────────────
# HTTP HANDLER
# ─────────────────────────────────────────────
class GitHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def serve_file(self, path: Path):
        if not path.exists():
            self.send_response(404)
            self.end_headers()
            return
        ct = {".html": "text/html; charset=utf-8", ".js": "application/javascript",
              ".css": "text/css", ".json": "application/json"}.get(path.suffix.lower(), "text/plain")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        params = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self.serve_file(STATIC_DIR / "index.html")
            return
        if path in ("/dashboard", "/dashboard.html"):
            self.serve_file(STATIC_DIR / "dashboard.html")
            return
        if path == "/api/projects":
            self.send_json(load_projects())
            return
        if path == "/api/ecosystem_status":
            self.send_json(ecosystem_status())
            return
        if path == "/api/ollama_models":
            self.send_json(get_ollama_models())
            return
        if path == "/api/bench_results":
            self.send_json(get_bench_results())
            return
        if path == "/api/todos":
            name = params.get("project", [""])[0]
            if name not in load_projects():
                self.send_json({"ok": False, "output": "Projeto nao encontrado"}, 404)
                return
            self.send_json({"ok": True, "todos": _read_todos(name)})
            return
        if path in ("/api/status", "/api/diff", "/api/log", "/api/branches"):
            name = params.get("project", [""])[0]
            projects = load_projects()
            if name not in projects:
                self.send_json({"ok": False, "output": "Projeto nao encontrado"}, 404)
                return
            proj_path = projects[name]["path"]
            if path == "/api/status":
                self.send_json(git_status(proj_path))
            elif path == "/api/diff":
                full = params.get("full", ["0"])[0] == "1"
                self.send_json(git_diff_full(proj_path) if full else git_diff(proj_path))
            elif path == "/api/log":
                self.send_json(git_log(proj_path))
            elif path == "/api/branches":
                self.send_json(git_branches(proj_path))
            return
        if path == "/api/detect_project":
            proj_path = params.get("path", [""])[0]
            if not proj_path:
                self.send_json({"ok": False, "output": "Caminho nao informado"}, 400)
                return
            self.send_json(detect_project_from_path(proj_path))
            return
        self.send_json({"ok": False, "output": "Rota nao encontrada"}, 404)

    def do_POST(self):
        length   = int(self.headers.get("Content-Length", 0))
        body     = json.loads(self.rfile.read(length) or b"{}")
        path     = urlparse(self.path).path
        projects = load_projects()

        def get_proj(b):
            name = b.get("project", "")
            return (projects[name]["path"], name) if name in projects else (None, name)

        if path == "/api/commit":
            proj_path, name = get_proj(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            msg = body.get("message", "").strip()
            if not msg:
                self.send_json({"ok": False, "output": "Mensagem de commit vazia"})
                return
            self.send_json(git_commit(proj_path, msg))
            return
        if path == "/api/push":
            proj_path, name = get_proj(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            self.send_json(git_push(proj_path, body.get("remote", "origin"), body.get("branch", "")))
            return
        if path == "/api/pull":
            proj_path, name = get_proj(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            self.send_json(git_pull(proj_path))
            return
        if path == "/api/checkout":
            proj_path, name = get_proj(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            branch = body.get("branch", "").strip()
            if not branch:
                self.send_json({"ok": False, "output": "Nome de branch vazio"})
                return
            self.send_json(git_checkout(proj_path, branch))
            return
        if path == "/api/new_branch":
            proj_path, name = get_proj(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            branch = body.get("branch", "").strip()
            if not branch:
                self.send_json({"ok": False, "output": "Nome de branch vazio"})
                return
            self.send_json(git_new_branch(proj_path, branch))
            return
        if path == "/api/open_vscode":
            proj_path, name = get_proj(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            self.send_json(open_vscode(proj_path))
            return
        if path == "/api/init":
            proj_path, name = get_proj(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            self.send_json(git_init(proj_path))
            return
        if path == "/api/add_project":
            name = body.get("name", "").strip()
            if not name:
                self.send_json({"ok": False, "output": "Nome do projeto vazio"})
                return
            if name in projects:
                self.send_json({"ok": False, "output": f"Projeto '{name}' ja existe"})
                return
            proj_path = body.get("path", "").strip()
            if not proj_path or not Path(proj_path).exists():
                self.send_json({"ok": False, "output": f"Pasta nao encontrada: {proj_path}"})
                return
            cfg = {
                "path": proj_path, "description": body.get("description", ""),
                "objective": body.get("objective", ""),
                "status": body.get("status", "em desenvolvimento"),
                "stack": [s.strip() for s in body.get("stack", "").split(",") if s.strip()],
                "type": body.get("type", "other"), "git_remote": body.get("git_remote", ""),
                "require_confirmation": ["git push", "git reset", "git rebase"],
            }
            result = save_project(name, cfg)
            if result["ok"] and body.get("init_git"):
                result["output"] += f"\n{git_init(proj_path)['output']}"
            self.send_json(result)
            return
        if path == "/api/edit_project":
            name = body.get("name", "").strip()
            if not name or name not in projects:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            existing = projects[name]
            cfg = {
                "path":        body.get("path", existing.get("path", "")).strip(),
                "description": body.get("description", existing.get("description", "")),
                "objective":   body.get("objective", existing.get("objective", "")),
                "status":      body.get("status", existing.get("status", "em desenvolvimento")),
                "stack":       [s.strip() for s in body.get("stack", "").split(",") if s.strip()],
                "type":        body.get("type", existing.get("type", "other")),
                "git_remote":  body.get("git_remote", existing.get("git_remote", "")),
                "require_confirmation": existing.get("require_confirmation", ["git push", "git reset", "git rebase"]),
            }
            self.send_json(save_project(name, cfg))
            return
        if path == "/api/remove_project":
            name = body.get("name", "").strip()
            if not name:
                self.send_json({"ok": False, "output": "Nome do projeto vazio"})
                return
            self.send_json(remove_project(name))
            return
        if path == "/api/ollama_models":
            self.send_json(get_ollama_models())
            return
        if path == "/api/generate_readme":
            proj_path, name = get_proj(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            cfg    = {**projects.get(name, {}), "name": name}
            result = generate_readme(proj_path, cfg, body.get("model", "phi3"))
            if result["ok"]:
                result["existing"] = get_existing_readme(proj_path)
            self.send_json(result)
            return
        if path == "/api/save_readme":
            proj_path, name = get_proj(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            content = body.get("content", "").strip()
            if not content:
                self.send_json({"ok": False, "output": "Conteudo vazio"})
                return
            self.send_json(save_readme(proj_path, content))
            return
        if path == "/api/suggest_commit":
            proj_path, name = get_proj(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            self.send_json(suggest_commit_message(
                proj_path,
                user_context=body.get("context", "").strip(),
                model=body.get("model", "phi3"),
                project_name=name,
                project_cfg=projects.get(name, {}),
            ))
            return
        if path == "/api/save_todos":
            _, name = get_proj(body)
            if name not in projects:
                self.send_json({"ok": False, "output": f"Projeto '{name}' nao encontrado"}, 404)
                return
            todos = body.get("todos", [])
            if not isinstance(todos, list):
                self.send_json({"ok": False, "output": "todos must be a list"})
                return
            normalised = []
            for item in todos:
                if isinstance(item, str):
                    normalised.append({"text": item, "done": False})
                elif isinstance(item, dict):
                    normalised.append({
                        "text": str(item.get("text", "")).strip(),
                        "done": bool(item.get("done", False)),
                    })
            normalised = [t for t in normalised if t["text"]]
            self.send_json(_save_todos(name, normalised))
            return
        self.send_json({"ok": False, "output": "Rota nao encontrada"}, 404)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
def main():
    STATIC_DIR.mkdir(exist_ok=True)
    TODOS_DIR.mkdir(exist_ok=True)
    print(f"Panda Git Manager")
    print(f"   http://localhost:{PORT}")
    print(f"   dashboard: http://localhost:{PORT}/dashboard")
    print(f"   PandaClient: {'loaded' if _PANDA_AVAILABLE else 'not found (fallback mode)'}")
    print(f"   todos dir:  {TODOS_DIR}")
    print()
    projects = load_projects()
    print(f"   {len(projects)} projetos carregados:")
    for name, cfg in projects.items():
        exists = "ok" if Path(cfg["path"]).exists() else "missing"
        print(f"   [{exists}] {name}")
    print()
    try:
        server = HTTPServer(("localhost", PORT), GitHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")


if __name__ == "__main__":
    main()
