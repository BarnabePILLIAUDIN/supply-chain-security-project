"""Orchestration de bout en bout : la chaîne complète (cas nominal) et le nettoyage."""
import shutil

from .config import Config
from . import cluster, image, sbom, signing


def run_full_chain(config: Config) -> None:
    """Chaîne complète build → déploiement : l'image légitime est ACCEPTÉE, pods Running."""
    image.check_tools(config)
    image.build_image(config)
    image.push_image(config)
    image.print_public_hint(config)
    sbom.generate_sbom(config)
    sbom.scan_image(config)
    signing.generate_keypair(config)
    signing.sign_image(config)
    signing.attest_image(config)
    cluster.create_cluster(config)
    cluster.install_kyverno(config)
    cluster.apply_policies(config)
    cluster.deploy_app(config)
    cluster.show_status(config)
    print("✅ Chaîne complète OK. Lancez 'attacks' pour la démo de blocage.")


def clean_all(config: Config) -> None:
    from .shell import run
    run(["k3d", "cluster", "delete", config.cluster], check=False)
    shutil.rmtree(config.local_dir, ignore_errors=True)
    print(f"  ✓ cluster supprimé + {config.local_dir} purgé")
