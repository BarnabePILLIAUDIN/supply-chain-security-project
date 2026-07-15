"""Contrôleur — traduit une sous-commande en appel du module métier correspondant.

Chaque sous-commande correspond à une étape des labs 0→4.
"""
import argparse
import sys

from . import attacks, cluster, image, manifests, pipeline, sbom, signing, verify
from .config import build_config

DESCRIPTION = """Orchestrateur de la chaîne d'approvisionnement logicielle en local.

Reproduit les labs 0→4 : build → SBOM → scan → signature → attestations → cluster k3d
→ Kyverno → politiques → déploiement → démo attaque/défense.

⚠️  cosign 2.x requis (--cosign ./cosign2) — la 3.x écrit via l'OCI referrers API que
    Kyverno 1.18 ne sait pas lire. Voir docs/04-depannage-local.md §1.
"""

# sous-commande -> fonction métier (chacune prend le Config résolu)
COMMANDS = {
    "tools": image.check_tools,
    "build": image.build_image,
    "login": image.print_login_hint,
    "push": image.push_image,
    "public": image.print_public_hint,
    "sbom": sbom.generate_sbom,
    "scan": sbom.scan_image,
    "scan-vuln": sbom.scan_vulnerable_demo,
    "keygen": signing.generate_keypair,
    "clean-sigs": signing.clean_signatures,
    "sign": signing.sign_image,
    "attest": signing.attest_image,
    "render": manifests.render_manifests,
    "cluster": cluster.create_cluster,
    "kyverno": cluster.install_kyverno,
    "policies": cluster.apply_policies,
    "deploy": cluster.deploy_app,
    "status": cluster.show_status,
    "attacks": attacks.run_attacks,
    "verify": verify.verify_artifacts,
    "clean": pipeline.clean_all,
    "all": pipeline.run_full_chain,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=list(COMMANDS), help="étape à exécuter")
    parser.add_argument("--user", help="propriétaire du package GHCR (défaut : $GHCR_USER, sinon $USER)")
    parser.add_argument("--tag", help="tag de build (défaut : 0.1.0)")
    parser.add_argument("--cluster", help="nom du cluster k3d (défaut : scs)")
    parser.add_argument("--namespace", help="namespace applicatif (défaut : app)")
    parser.add_argument("--host-port", help="port hôte mappé sur le NodePort 30080 (défaut : 8080)")
    parser.add_argument("--cosign", help="binaire cosign — 2.x requis (défaut : cosign du PATH)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = build_config(args)
        COMMANDS[args.command](config)
        return 0
    except RuntimeError as error:
        sys.stderr.write(f"\n✗ {error}\n")
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("\n✗ interrompu\n")
        return 130
