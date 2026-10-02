"""Publica uma versão nova: gera o executável e o instalador e cria a release no GitHub (sem GitHub Actions).

Uso:  python tools/release.py 1.2.0 [--notas "o que mudou"]

1. confere que o git está limpo, na main e em dia com o GitHub
2. grava a versão em creeper/__init__.py e gera o executável e o instalador (tools/build_exe.py)
3. mostra as notas e pergunta se pode publicar
4. commit "Versão 1.2.0", tag v1.2.0, push e release no GitHub com os dois anexados
5. na primeira vez, liga o GitHub Pages (a página de download, que fica em docs/)

Sem --notas, as notas são os títulos dos commits desde a última versão (é o que o tutor lê na janela
"versão nova"). Os creepers rodando por aí descobrem em até 6 horas, ou 1 minuto depois de abrirem.
Precisa do GitHub CLI logado (uma vez só):  gh auth login
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
INIT = ROOT / "creeper" / "__init__.py"
PAGE_URL = "https://leandroneckel.github.io/creeper_companion/"

import build_exe  # noqa: E402
from creeper import __version__ as CURRENT, updater  # noqa: E402


def run(*cmd: str, check: bool = True) -> str:
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if check and result.returncode != 0:
        sys.exit(f"Falhou: {' '.join(cmd)}\n{result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def set_version(version: str) -> None:
    text = INIT.read_text(encoding="utf-8")
    INIT.write_text(re.sub(r'__version__ = "[^"]*"', f'__version__ = "{version}"', text), encoding="utf-8")


def default_notes() -> str:
    previous = run("git", "describe", "--tags", "--abbrev=0", check=False)
    log = run("git", "log", "--no-merges", "--pretty=format:%s", f"{previous}..HEAD" if previous else "HEAD")
    lines = [f"- {s}" for s in log.splitlines() if s and not re.fullmatch(r"Versão \d+\.\d+\.\d+", s)]
    return "\n".join(lines) or "- Pequenas melhorias."


def ensure_pages() -> None:
    """Liga o GitHub Pages servindo a pasta docs/ da main (a página de download), se ainda não estiver."""
    exists = subprocess.run(["gh", "api", f"repos/{updater.REPO}/pages", "--silent"], cwd=ROOT,
                            capture_output=True).returncode == 0
    if not exists:
        run("gh", "api", "-X", "POST", f"repos/{updater.REPO}/pages",
            "-f", "source[branch]=main", "-f", "source[path]=/docs")
        run("gh", "repo", "edit", updater.REPO, "--homepage", PAGE_URL)
        print(f"Página de download ligada (leva uns minutos pra aparecer na primeira vez): {PAGE_URL}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica uma versão nova do Creeper Companion.")
    parser.add_argument("versao", help="ex.: 1.2.0")
    parser.add_argument("--notas", help="o que mudou (markdown); sem isso, usa os títulos dos commits")
    args = parser.parse_args()

    version = args.versao.strip().lstrip("vV")
    tag = f"v{version}"
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit("A versão tem que ser no formato 1.2.0")
    if updater.newer(CURRENT, version):
        sys.exit(f"{version} é mais velha que a versão atual do código ({CURRENT}).")

    if not shutil.which("gh"):
        sys.exit("Falta o GitHub CLI: https://cli.github.com (depois: gh auth login)")
    run("gh", "auth", "status")
    if sys.platform == "win32" and not build_exe.find_iscc():
        sys.exit("Falta o Inno Setup 6, que gera o instalador:  winget install JRSoftware.InnoSetup")
    if run("git", "status", "--porcelain"):
        sys.exit("Tem mudanças sem commit. Faça o commit (ou guarde) antes de publicar.")
    if run("git", "branch", "--show-current") != "main":
        sys.exit("Publique a partir da main.")
    run("git", "fetch", "origin", "--tags")
    if run("git", "rev-list", "--count", "HEAD..origin/main") != "0":
        sys.exit("A main daqui está atrás da do GitHub: faça git pull antes.")
    if run("git", "tag", "-l", tag):
        sys.exit(f"A tag {tag} já existe.")

    notes = args.notas.strip() if args.notas else default_notes()
    bumped = version != CURRENT
    if bumped:
        set_version(version)
    try:
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_exe.py")], cwd=ROOT, check=True)
    except subprocess.CalledProcessError:
        if bumped:
            set_version(CURRENT)
        sys.exit("O executável não foi gerado; nada foi publicado.")
    assets = [build_exe.exe_path()]
    if sys.platform == "win32":
        assets.insert(0, build_exe.setup_path())

    files = ", ".join(f"{a.name} ({a.stat().st_size / 1e6:.1f} MB)" for a in assets)
    print(f"\nVersão {version}: {files}\nNotas:\n{notes}\n")
    if input(f"Publicar {tag} no GitHub? [s/N] ").strip().lower() not in ("s", "sim"):
        if bumped:
            set_version(CURRENT)
        sys.exit("Nada foi publicado (os arquivos ficaram em dist/ pra você testar).")

    if bumped:
        run("git", "add", str(INIT))
        run("git", "commit", "-m", f"Versão {version}")
    run("git", "tag", "-a", tag, "-m", f"Versão {version}")
    run("git", "push", "origin", "main", tag)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(notes)
    run("gh", "release", "create", tag, *map(str, assets), "--title", f"Versão {version}",
        "--notes-file", f.name, "--verify-tag")
    Path(f.name).unlink(missing_ok=True)
    print("Publicada:", run("gh", "release", "view", tag, "--json", "url", "-q", ".url"))
    ensure_pages()
    print(f"Link pra mandar pras pessoas: {PAGE_URL}")


if __name__ == "__main__":
    main()
