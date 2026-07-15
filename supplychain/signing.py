"""Lab 2 — signer l'image (cosign, par clé) et attacher les attestations SBOM + provenance."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .shell import cosign_env, git_commit, git_remote, read_digest, run


def generate_keypair(config: Config) -> None:
    if config.cosign_key.exists():
        print("  ✓ cosign.key déjà présent")
        return
    run([config.cosign, "generate-key-pair"], cwd=config.repo_root, extra_env=cosign_env(config))


def clean_signatures(config: Config) -> None:
    """Purge signatures + attestations existantes (GHCR refuse le DELETE : échec toléré)."""
    digest = read_digest(config)
    run([config.cosign, "clean", "--force", "--type", "all", digest],
        check=False, extra_env=cosign_env(config))


def sign_image(config: Config) -> None:
    digest = read_digest(config)
    run([config.cosign, "sign", "--key", str(config.cosign_key), "--yes", digest],
        extra_env=cosign_env(config))


def attest_image(config: Config) -> None:
    """Attache une attestation SBOM (niveau paquets, < 2 Mio) puis une attestation de provenance."""
    digest = read_digest(config)
    packages_sbom = _write_packages_only_sbom(config)
    run([config.cosign, "attest", "--key", str(config.cosign_key), "--yes",
         "--predicate", str(packages_sbom), "--type", "spdxjson", digest],
        extra_env=cosign_env(config))

    provenance = _write_provenance(config)
    run([config.cosign, "attest", "--key", str(config.cosign_key), "--yes",
         "--predicate", str(provenance), "--type", "slsaprovenance", digest],
        extra_env=cosign_env(config))


def _write_packages_only_sbom(config: Config) -> Path:
    """Réduit le SBOM SPDX à ses PAQUETS (sans `files`) pour tenir sous la limite de
    contexte de 2 Mio de Kyverno lors de la vérification d'attestation."""
    full = json.loads((config.local_dir / "sbom.spdx.json").read_text())
    full.pop("files", None)
    references_file = lambda rel: (
        rel.get("spdxElementId", "").startswith("SPDXRef-File-")
        or rel.get("relatedSpdxElement", "").startswith("SPDXRef-File-")
    )
    full["relationships"] = [rel for rel in full.get("relationships", []) if not references_file(rel)]
    destination = config.local_dir / "sbom.att.spdx.json"
    destination.write_text(json.dumps(full))
    return destination


def _write_provenance(config: Config) -> Path:
    """Predicate de provenance SLSA (v0.2 simplifié) ; en CI il serait généré par le workflow."""
    predicate = {
        "buildType": "https://example.com/manual-local-build/v1",
        "builder": {"id": f"local:{config.ghcr_user}"},
        "invocation": {
            "configSource": {
                "uri": f"git+{git_remote(config)}",
                "digest": {"sha1": git_commit(config)},
            }
        },
        "metadata": {"buildStartedOn": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
    }
    destination = config.local_dir / "provenance.json"
    destination.write_text(json.dumps(predicate, indent=2))
    return destination
