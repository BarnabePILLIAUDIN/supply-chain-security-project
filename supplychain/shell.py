"""Primitives partagées : exécution de commandes, environnement cosign, helpers git & FS.

Module feuille (ne dépend que de `config`). Toute commande externe passe par `run`, qui
l'affiche et échoue vite avec contexte — pas d'échec silencieux.
"""
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from .config import Config


def run(cmd, *, capture=False, check=True, cwd=None, extra_env=None) -> subprocess.CompletedProcess:
    """Lance `cmd` en l'affichant ; lève RuntimeError avec contexte si l'appel échoue."""
    shown = " ".join(shlex.quote(part) for part in cmd)
    print(f"  $ {shown}", flush=True)  # flush : garder l'ordre avec la sortie du sous-processus
    completed = subprocess.run(
        cmd, text=True, cwd=cwd,
        env={**os.environ, **(extra_env or {})},
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if check and completed.returncode != 0:
        detail = f"\n{completed.stdout}" if (capture and completed.stdout) else ""
        raise RuntimeError(f"commande échouée (code {completed.returncode}) : {shown}{detail}")
    return completed


def cosign_env(config: Config) -> dict:
    """cosign lit le mot de passe de sa clé dans l'environnement (vide = clé de démo)."""
    return {"COSIGN_PASSWORD": config.cosign_password}


def tool_available(tool: str) -> bool:
    if "/" in tool:
        return Path(tool).exists() and os.access(tool, os.X_OK)
    return shutil.which(tool) is not None


def read_digest(config: Config) -> str:
    """Lit le digest immuable capturé au push (échoue si l'étape push n'a pas eu lieu)."""
    if not config.digest_file.exists():
        raise RuntimeError(f"digest inconnu ({config.digest_file}) — lancez 'push' d'abord.")
    return config.digest_file.read_text().strip()


def copy_app_to_temp_context(config: Config, name: str) -> Path:
    """Copie app/ dans un contexte de build jetable sous .local/ (le dépôt reste intact)."""
    context = config.local_dir / name
    shutil.rmtree(context, ignore_errors=True)
    shutil.copytree(config.repo_root / "app", context)
    return context


def git_commit(config: Config) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.repo_root, capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def git_remote(config: Config) -> str:
    result = subprocess.run(["git", "config", "--get", "remote.origin.url"],
                            cwd=config.repo_root, capture_output=True, text=True)
    return result.stdout.strip() or "local"
