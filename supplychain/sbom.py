"""Lab 1 — générer le SBOM et scanner les vulnérabilités (gate qui casse la chaîne)."""
from pathlib import Path

from .config import Config
from .image import export_image_archive
from .shell import copy_app_to_temp_context, run


def generate_sbom(config: Config) -> None:
    archive = export_image_archive(config)
    sbom = config.local_dir / "sbom.spdx.json"
    catalogued = run(["syft", f"docker-archive:{archive}", "-o", "spdx-json"], capture=True)
    sbom.write_text(catalogued.stdout)
    print(f"  ✓ {sbom}")


def scan_image(config: Config) -> None:
    """Gate : grype lit .grype.yaml et sort != 0 sur une CVE CRITICAL corrigeable."""
    archive = export_image_archive(config)
    run(["grype", f"docker-archive:{archive}"], cwd=config.repo_root)


def scan_vulnerable_demo(config: Config, old_flask: str = "2.0.1") -> None:
    """Lab 1.4 — injecte un Flask vulnérable dans un contexte TEMPORAIRE et prouve que la gate casse."""
    context = copy_app_to_temp_context(config, "vuln-ctx")
    _pin_flask_version(context / "requirements.txt", old_flask)
    print(f"  Flask épinglé à {old_flask} (requirements.txt du dépôt intact)")

    run(["docker", "build", "-q", "-t", f"{config.img}:vuln", str(context)])
    archive = config.local_dir / "vuln.tar"
    run(["docker", "save", f"{config.img}:vuln", "-o", str(archive)])

    print("  ▶ grype --only-fixed --fail-on high")
    result = run(
        ["grype", f"docker-archive:{archive}", "--only-fixed", "--fail-on", "high"],
        capture=True, check=False,
    )
    for line in result.stdout.splitlines():
        if any(token in line.lower() for token in ("name", "flask", "werkzeug", "jinja")):
            print(f"    {line}")
    if result.returncode != 0:
        print(f"  ✅ CHAÎNE CASSÉE (grype code={result.returncode}) — CVE Flask HIGH corrigeable.")
    else:
        print("  ❌ grype code=0 — la gate n'a pas cassé (inattendu).")


def _pin_flask_version(requirements: Path, version: str) -> None:
    lines = requirements.read_text().splitlines()
    patched = [f"Flask=={version}" if line.startswith("Flask==") else line for line in lines]
    requirements.write_text("\n".join(patched) + "\n")
