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
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
        output = result.stdout or result.stderr or "(sem output)"
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


def git_commit(path: str, message: str) -> dict:
    run_git(path, ["add", "."])
    return run_git(path, ["commit", "-m", message])


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



    return run_git(path, ["init"])


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


# ─────────────────────────────────────────────
# HTTP HANDLER
# ─────────────────────────────────────────────
class GitHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Suprime logs verbosos do servidor
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

        # ── Arquivos estáticos ──────────────────
        if path == "/" or path == "/index.html":
            self.serve_file(STATIC_DIR / "index.html")
            return

        # ── API ─────────────────────────────────
        if path == "/api/projects":
            projects = load_projects()
            self.send_json(projects)
            return

        if path == "/api/status":
            name = params.get("project", [""])[0]
            projects = load_projects()
            if name not in projects:
                self.send_json({"ok": False, "output": "Projeto não encontrado"}, 404)
                return
            proj_path = projects[name]["path"]
            self.send_json(git_status(proj_path))
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
            remote = body.get("remote", "origin")
            branch = body.get("branch", "")
            self.send_json(git_push(proj_path, remote, branch))
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
                "path": proj_path,
                "description": body.get("description", ""),
                "objective":   body.get("objective", ""),
                "status":      body.get("status", "em desenvolvimento"),
                "stack":       [s.strip() for s in body.get("stack", "").split(",") if s.strip()],
                "type":        body.get("type", "other"),
                "git_remote":  body.get("git_remote", ""),
                "require_confirmation": ["git push", "git reset", "git rebase"],
            }

            result = save_project(name, cfg)

            # git init opcional
            if result["ok"] and body.get("init_git"):
                init_result = git_init(proj_path)
                result["output"] += f"\n{init_result['output']}"

            self.send_json(result)
            return
            return

        self.send_json({"ok": False, "output": "Rota não encontrada"}, 404)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
def main():
    STATIC_DIR.mkdir(exist_ok=True)
    print(f"🐼 Git Manager")
    print(f"   http://localhost:{PORT}")
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
