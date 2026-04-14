"""
server.py — Git Manager local
Servidor HTTP embutido do Python, zero dependências externas.

Uso:
    python server.py
    Abra: http://localhost:8765
"""

import json
import os
import subprocess
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ── PandaClient (shared LLM module) ─────────────────────────────────────────
# Imports from pandagent — single point of contact with Ollama.
_PANDAGENT_PATH = str(Path(__file__).parent.parent / "pandagent")
if _PANDAGENT_PATH not in sys.path:
    sys.path.insert(0, _PANDAGENT_PATH)

try:
    from panda_client import PandaClient
    _panda = PandaClient()
    _PANDA_AVAILABLE = True
except ImportError:
    _PANDA_AVAILABLE = False

PROJECTS_FILE = Path(__file__).parent / "projects.json"
PORT = 8765
STATIC_DIR = Path(__file__).parent / "static"


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
    """Executa comando git e retorna stdout/stderr/code."""
    if not Path(path).exists():
        return {"ok": False, "output": f"Pasta não encontrada: {path}", "code": -1}
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout or result.stderr or "(no output)"
        return {"ok": result.returncode == 0, "output": output.strip(), "code": result.returncode}
    except FileNotFoundError:
        return {"ok": False, "output": "Git não encontrado. Instale o git.", "code": -1}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "Timeout — comando demorou mais de 30s.", "code": -1}
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
    """Inicializa um repositório git na pasta."""
    return run_git(path, ["init"])


def git_new_branch(path: str, branch: str) -> dict:
    """Cria e faz checkout de uma nova branch."""
    return run_git(path, ["checkout", "-b", branch])


def git_commit(path: str, message: str) -> dict:
    run_git(path, ["add", "."])
    return run_git(path, ["commit", "-m", message])


def git_diff_staged(path: str) -> dict:
    """Retorna o diff staged (git add já feito) ou unstaged se não houver staged."""
    staged = run_git(path, ["diff", "--cached"])
    if staged["ok"] and staged["output"] and staged["output"] != "(no output)":
        return staged
    return run_git(path, ["diff"])


def get_ollama_models() -> dict:
    """Returns installed Ollama models via PandaClient."""
    if _PANDA_AVAILABLE:
        models = _panda.available_models()
        if models:
            return {"ok": True, "models": models}
        return {"ok": False, "models": [], "output": "Ollama unavailable or no models installed."}
    # Fallback direto caso PandaClient não esteja disponível
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags", method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "models": [m["name"] for m in result.get("models", [])]}
    except Exception as e:
        return {"ok": False, "models": [], "output": f"Ollama unavailable: {e}"}


def scan_project_structure(path: str) -> str:
    """Escaneia a estrutura do projeto para contextualizar o LLM."""
    root = Path(path)
    ignore = {'.git', 'node_modules', '__pycache__', '.next', 'dist', 'build', '.env', 'venv', '.venv'}

    lines = []
    for item in sorted(root.rglob('*')):
        if any(p in item.parts for p in ignore):
            continue
        rel = item.relative_to(root)
        depth = len(rel.parts) - 1
        if depth > 3:
            continue
        prefix = '  ' * depth
        if item.is_dir():
            lines.append(f"{prefix}[{rel.name}/]")
        else:
            lines.append(f"{prefix}{rel.name}")

    # Lê arquivos de contexto se existirem
    extras = []
    for fname in ['package.json', 'requirements.txt', 'pyproject.toml', 'Cargo.toml']:
        fpath = root / fname
        if fpath.exists():
            try:
                content = fpath.read_text(encoding='utf-8', errors='replace')[:800]
                extras.append(f"\n--- {fname} ---\n{content}")
            except Exception:
                pass

    return '\n'.join(lines) + ''.join(extras)


def get_existing_readme(path: str) -> str:
    """Retorna o conteúdo do README.md existente ou string vazia."""
    readme = Path(path) / 'README.md'
    if readme.exists():
        try:
            return readme.read_text(encoding='utf-8', errors='replace')
        except Exception:
            pass
    return ''


def save_readme(path: str, content: str) -> dict:
    """Salva o README.md no projeto."""
    try:
        readme = Path(path) / 'README.md'
        readme.write_text(content, encoding='utf-8')
        return {'ok': True, 'output': 'README.md salvo com sucesso.'}
    except Exception as e:
        return {'ok': False, 'output': str(e)}


def generate_readme(path: str, project_cfg: dict, model: str = "phi3") -> dict:
    """Generates a README.md using PandaClient."""
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

    # Fallback direto caso PandaClient não esteja disponível
    name        = project_cfg.get("name", Path(path).name)
    description = project_cfg.get("description", "")
    objective   = project_cfg.get("objective", "")
    stack       = ", ".join(project_cfg.get("stack", []))
    status      = project_cfg.get("status", "")

    prompt = f"""You are a technical writer. Generate a clean and professional README.md in English for the project below.

Use markdown. Include: project name, short description, what it does, main features, stack, how to run (if inferable), and project structure.
Do NOT include license section. Keep it concise and developer-focused.
Reply ONLY with the raw markdown content, no explanations, no code fences around the whole file.

Project name: {name}
Description: {description}
Objective: {objective}
Stack: {stack}
Status: {status}

File structure:
{structure}
"""
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=None) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result.get("response", "").strip()
            if not content:
                return {"ok": False, "output": "Ollama returned empty response."}
            return {"ok": True, "output": content}
    except Exception as e:
        return {"ok": False, "output": f"Ollama error: {e}"}


def suggest_commit_message(path: str, user_context: str = "", model: str = "phi3") -> dict:
    """Suggests a commit message using PandaClient."""
    diff   = git_diff_staged(path)
    status = git_status(path)

    diff_text   = diff.get("output", "").strip()
    status_text = status.get("output", "").strip()

    if _PANDA_AVAILABLE:
        _panda.text_model = model
        return _panda.commit_message(
            diff=diff_text,
            status=status_text,
            extra_context=user_context,
        )

    # Fallback direto caso PandaClient não esteja disponível
    context_block = f"\nDeveloper context: {user_context}" if user_context.strip() else ""
    prompt = f"""You are a development assistant. Analyze the diff and status below and generate ONE clear and objective commit message in English, following the conventional commits standard (feat, fix, refactor, docs, chore, etc).

Reply ONLY with the commit message, no explanations, no quotes, no extra prefix.
{context_block}

Status:
{status_text}

Diff:
{diff_text[:3000]}
"""
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=None) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            message = result.get("response", "").strip()
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
    """Abre a pasta no VS Code."""
    if not Path(path).exists():
        return {"ok": False, "output": f"Pasta não encontrada: {path}"}
    try:
        subprocess.Popen(["code", path], shell=True)
        return {"ok": True, "output": f"Abrindo no VS Code: {path}"}
    except Exception as e:
        return {"ok": False, "output": str(e)}


def detect_project_from_path(path: str) -> dict:
    """Detecta informações do projeto a partir de uma pasta com .git."""
    root = Path(path)
    if not root.exists():
        return {"ok": False, "output": f"Pasta não encontrada: {path}"}
    if not (root / ".git").exists():
        return {"ok": False, "output": "Nenhum repositório .git encontrado nesta pasta."}

    name = root.name

    remote = run_git(path, ["remote", "get-url", "origin"])
    git_remote = remote["output"] if remote["ok"] else ""

    stack_hints = {
        "package.json":     "javascript",
        "requirements.txt": "python",
        "pyproject.toml":   "python",
        "Cargo.toml":       "rust",
        "go.mod":           "go",
        "pom.xml":          "java",
        "*.sol":            "solidity",
    }
    stack = []
    for fname, lang in stack_hints.items():
        if fname.startswith("*"):
            ext = fname[1:]
            if any(root.glob(f"**/*{ext}")):
                stack.append(lang)
        elif (root / fname).exists():
            stack.append(lang)

    project_type = "other"
    if any(root.glob("**/*.sol")):
        project_type = "contract"
    elif (root / "package.json").exists():
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8", errors="replace"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if any(k in deps for k in ["next", "react", "vue", "svelte"]):
                project_type = "frontend"
        except Exception:
            pass
    elif any(root.glob("**/*.py")):
        project_type = "tool"

    return {
        "ok":         True,
        "name":       name,
        "path":       str(root),
        "git_remote": git_remote.strip(),
        "stack":      stack,
        "type":       project_type,
    }


def save_project(name: str, cfg: dict) -> dict:
    """Adiciona ou atualiza um projeto no projects.json."""
    try:
        if PROJECTS_FILE.exists():
            with open(PROJECTS_FILE, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"projects": {}, "settings": {}}

        data["projects"][name] = cfg

        with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {"ok": True, "output": f"Projeto '{name}' salvo com sucesso."}
    except Exception as e:
        return {"ok": False, "output": str(e)}


def remove_project(name: str) -> dict:
    """Remove um projeto do projects.json sem deletar a pasta."""
    try:
        if not PROJECTS_FILE.exists():
            return {"ok": False, "output": "projects.json não encontrado"}
        with open(PROJECTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if name not in data.get("projects", {}):
            return {"ok": False, "output": f"Projeto '{name}' não encontrado"}
        del data["projects"][name]
        with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"ok": True, "output": f"Projeto '{name}' removido com sucesso."}
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
        ext = path.suffix.lower()
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".js":   "application/javascript",
            ".css":  "text/css",
            ".json": "application/json",
        }
        ct = content_types.get(ext, "text/plain")
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

        if path == "/" or path == "/index.html":
            self.serve_file(STATIC_DIR / "index.html")
            return

        if path == "/api/projects":
            self.send_json(load_projects())
            return

        if path == "/api/status":
            name = params.get("project", [""])[0]
            projects = load_projects()
            if name not in projects:
                self.send_json({"ok": False, "output": "Projeto não encontrado"}, 404)
                return
            self.send_json(git_status(projects[name]["path"]))
            return

        if path == "/api/diff":
            name = params.get("project", [""])[0]
            full = params.get("full", ["0"])[0] == "1"
            projects = load_projects()
            if name not in projects:
                self.send_json({"ok": False, "output": "Projeto não encontrado"}, 404)
                return
            proj_path = projects[name]["path"]
            result = git_diff_full(proj_path) if full else git_diff(proj_path)
            self.send_json(result)
            return

        if path == "/api/log":
            name = params.get("project", [""])[0]
            projects = load_projects()
            if name not in projects:
                self.send_json({"ok": False, "output": "Projeto não encontrado"}, 404)
                return
            self.send_json(git_log(projects[name]["path"]))
            return

        if path == "/api/ollama_models":
            self.send_json(get_ollama_models())
            return

        if path == "/api/detect_project":
            proj_path = params.get("path", [""])[0]
            if not proj_path:
                self.send_json({"ok": False, "output": "Caminho não informado"}, 400)
                return
            self.send_json(detect_project_from_path(proj_path))
            return

        if path == "/api/branches":
            name = params.get("project", [""])[0]
            projects = load_projects()
            if name not in projects:
                self.send_json({"ok": False, "output": "Projeto não encontrado"}, 404)
                return
            self.send_json(git_branches(projects[name]["path"]))
            return

        self.send_json({"ok": False, "output": "Rota não encontrada"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")
        parsed = urlparse(self.path)
        path   = parsed.path
        projects = load_projects()

        def get_project_path(b):
            name = b.get("project", "")
            if name not in projects:
                return None, name
            return projects[name]["path"], name

        if path == "/api/commit":
            proj_path, name = get_project_path(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' não encontrado"}, 404)
                return
            message = body.get("message", "").strip()
            if not message:
                self.send_json({"ok": False, "output": "Mensagem de commit vazia"})
                return
            self.send_json(git_commit(proj_path, message))
            return

        if path == "/api/push":
            proj_path, name = get_project_path(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' não encontrado"}, 404)
                return
            self.send_json(git_push(proj_path, body.get("remote", "origin"), body.get("branch", "")))
            return

        if path == "/api/pull":
            proj_path, name = get_project_path(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' não encontrado"}, 404)
                return
            self.send_json(git_pull(proj_path))
            return

        if path == "/api/checkout":
            proj_path, name = get_project_path(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' não encontrado"}, 404)
                return
            branch = body.get("branch", "").strip()
            if not branch:
                self.send_json({"ok": False, "output": "Nome de branch vazio"})
                return
            self.send_json(git_checkout(proj_path, branch))
            return

        if path == "/api/new_branch":
            proj_path, name = get_project_path(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' não encontrado"}, 404)
                return
            branch = body.get("branch", "").strip()
            if not branch:
                self.send_json({"ok": False, "output": "Nome de branch vazio"})
                return
            self.send_json(git_new_branch(proj_path, branch))
            return

        if path == "/api/open_vscode":
            proj_path, name = get_project_path(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' não encontrado"}, 404)
                return
            self.send_json(open_vscode(proj_path))
            return

        if path == "/api/init":
            proj_path, name = get_project_path(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' não encontrado"}, 404)
                return
            self.send_json(git_init(proj_path))
            return

        if path == "/api/add_project":
            name = body.get("name", "").strip()
            if not name:
                self.send_json({"ok": False, "output": "Nome do projeto vazio"})
                return
            if name in projects:
                self.send_json({"ok": False, "output": f"Projeto '{name}' já existe"})
                return
            proj_path = body.get("path", "").strip()
            if not proj_path:
                self.send_json({"ok": False, "output": "Caminho vazio"})
                return
            if not Path(proj_path).exists():
                self.send_json({"ok": False, "output": f"Pasta não encontrada: {proj_path}"})
                return
            cfg = {
                "path":        proj_path,
                "description": body.get("description", ""),
                "objective":   body.get("objective", ""),
                "status":      body.get("status", "em desenvolvimento"),
                "stack":       [s.strip() for s in body.get("stack", "").split(",") if s.strip()],
                "type":        body.get("type", "other"),
                "git_remote":  body.get("git_remote", ""),
                "require_confirmation": ["git push", "git reset", "git rebase"],
            }
            result = save_project(name, cfg)
            if result["ok"] and body.get("init_git"):
                init_result = git_init(proj_path)
                result["output"] += f"\n{init_result['output']}"
            self.send_json(result)
            return

        if path == "/api/edit_project":
            name = body.get("name", "").strip()
            if not name or name not in projects:
                self.send_json({"ok": False, "output": f"Projeto '{name}' não encontrado"}, 404)
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
            proj_path, name = get_project_path(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' não encontrado"}, 404)
                return
            model = body.get("model", "phi3")
            cfg = {**projects.get(name, {}), "name": name}
            existing = get_existing_readme(proj_path)
            result = generate_readme(proj_path, cfg, model)
            if result["ok"]:
                result["existing"] = existing
            self.send_json(result)
            return

        if path == "/api/save_readme":
            proj_path, name = get_project_path(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' não encontrado"}, 404)
                return
            content = body.get("content", "").strip()
            if not content:
                self.send_json({"ok": False, "output": "Conteúdo vazio"})
                return
            self.send_json(save_readme(proj_path, content))
            return

        if path == "/api/suggest_commit":
            proj_path, name = get_project_path(body)
            if not proj_path:
                self.send_json({"ok": False, "output": f"Projeto '{name}' não encontrado"}, 404)
                return
            self.send_json(suggest_commit_message(
                proj_path,
                user_context=body.get("context", "").strip(),
                model=body.get("model", "phi3"),
            ))
            return

        self.send_json({"ok": False, "output": "Rota não encontrada"}, 404)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
def main():
    STATIC_DIR.mkdir(exist_ok=True)
    print(f"🐼 Git Manager")
    print(f"   http://localhost:{PORT}")
    print(f"   PandaClient: {'✅ loaded' if _PANDA_AVAILABLE else '⚠️  not found (fallback mode)'}")
    print(f"   Ctrl+C para encerrar\n")

    projects = load_projects()
    print(f"   {len(projects)} projetos carregados:")
    for name, cfg in projects.items():
        exists = "✅" if Path(cfg["path"]).exists() else "❌"
        print(f"   {exists} {name}")
    print()

    try:
        server = HTTPServer(("localhost", PORT), GitHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")


if __name__ == "__main__":
    main()
