"""Lab 3 — cluster k3d, installation de Kyverno, politiques d'admission et déploiement."""
import subprocess

from .config import Config
from .manifests import render_manifests
from .shell import run

KYVERNO_MANIFEST = "https://github.com/kyverno/kyverno/releases/latest/download/install.yaml"
POLICIES = ["01-allowed-registries", "02-disallow-latest", "03-verify-signature", "04-require-provenance"]


def create_cluster(config: Config) -> None:
    if _cluster_exists(config):
        print(f"  ✓ cluster {config.cluster} déjà présent")
        return
    source = (config.repo_root / "cluster" / "k3d-config.yaml").read_text()
    rendered = config.local_dir / "k3d-config.yaml"
    rendered.write_text(source.replace("8080:30080", f"{config.host_port}:30080"))
    run(["k3d", "cluster", "create", "--config", str(rendered)])


def install_kyverno(config: Config) -> None:
    # --server-side : les CRD Kyverno dépassent la limite d'annotation de 262144 o du
    # `kubectl apply` client-side ; le server-side apply l'évite et reste idempotent
    # (fonctionne que Kyverno soit déjà installé ou non).
    run(["kubectl", "apply", "--server-side", "--force-conflicts", "-f", KYVERNO_MANIFEST])
    run(["kubectl", "-n", "kyverno", "rollout", "status",
         "deploy/kyverno-admission-controller", "--timeout=180s"])


def apply_policies(config: Config) -> None:
    render_manifests(config)
    _ensure_namespace(config)
    for policy in POLICIES:
        run(["kubectl", "apply", "-f", str(config.local_dir / f"{policy}.yaml")])
    run(["kubectl", "get", "clusterpolicy"])


def deploy_app(config: Config) -> None:
    render_manifests(config)
    run(["kubectl", "apply", "-n", config.namespace, "-f", str(config.local_dir / "deployment.yaml")])
    run(["kubectl", "-n", config.namespace, "rollout", "status",
         "deploy/scs-demo-app", "--timeout=120s"])


def show_status(config: Config) -> None:
    run(["kubectl", "get", "clusterpolicy"])
    run(["kubectl", "get", "pods", "-n", config.namespace, "-o", "wide"])


def _cluster_exists(config: Config) -> bool:
    result = subprocess.run(["k3d", "cluster", "list", config.cluster], capture_output=True, text=True)
    return result.returncode == 0 and config.cluster in result.stdout


def _ensure_namespace(config: Config) -> None:
    run(["kubectl", "create", "namespace", config.namespace], check=False, capture=True)
