"""Configuration du run, résolue une fois (env < CLI) puis passée explicitement partout.

C'est le seul état partagé : un objet immuable, injecté dans chaque fonction — pas de global.
"""
import argparse
import os
from dataclasses import dataclass
from pathlib import Path

GHCR_PACKAGE = "scs-demo-app"


@dataclass(frozen=True)
class Config:
    ghcr_user: str
    tag: str
    cluster: str
    namespace: str
    host_port: str
    cosign: str
    cosign_password: str
    repo_root: Path

    @property
    def img(self) -> str:
        return f"ghcr.io/{self.ghcr_user}/{GHCR_PACKAGE}"

    @property
    def local_dir(self) -> Path:
        return self.repo_root / ".local"

    @property
    def cosign_key(self) -> Path:
        return self.repo_root / "cosign.key"

    @property
    def cosign_pub(self) -> Path:
        return self.repo_root / "cosign.pub"

    @property
    def digest_file(self) -> Path:
        return self.local_dir / "digest"


def build_config(args: argparse.Namespace) -> Config:
    """Résout chaque paramètre : valeur CLI si fournie, sinon variable d'env, sinon défaut."""
    pick = lambda cli, env_key, default: cli or os.environ.get(env_key) or default
    # user GHCR : --user > $GHCR_USER > $USER (login shell). Aucun défaut codé en dur.
    ghcr_user = args.user or os.environ.get("GHCR_USER") or os.environ.get("USER")
    if not ghcr_user:
        raise RuntimeError("user GHCR introuvable : passez --user <nom> ou exportez GHCR_USER (ou USER).")
    config = Config(
        ghcr_user=ghcr_user,
        tag=pick(args.tag, "TAG", "0.1.0"),
        cluster=pick(args.cluster, "CLUSTER", "scs"),
        namespace=pick(args.namespace, "NAMESPACE", "app"),
        host_port=pick(args.host_port, "HOST_PORT", "8080"),
        cosign=pick(args.cosign, "COSIGN", "cosign"),
        cosign_password=os.environ.get("COSIGN_PASSWORD", ""),
        repo_root=Path(__file__).resolve().parent.parent,
    )
    config.local_dir.mkdir(exist_ok=True)
    return config
