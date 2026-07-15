"""Lab 0 — construire, publier et exporter l'image de l'application."""
from pathlib import Path

from .config import Config, GHCR_PACKAGE
from .shell import git_commit, run, tool_available

REQUIRED_TOOLS = ["docker", "k3d", "kubectl", "syft", "grype", "jq"]


def check_tools(config: Config) -> None:
    tools = REQUIRED_TOOLS + [config.cosign]
    missing = [tool for tool in tools if not tool_available(tool)]
    for tool in tools:
        print(f"  {'✓' if tool not in missing else '✗ MANQUANT'} {tool}")
    if missing:
        raise RuntimeError(f"outils manquants : {', '.join(missing)}")


def build_image(config: Config) -> None:
    source_url = f"https://github.com/{config.ghcr_user}/supply-chain-security-project"
    run([
        "docker", "build", "-t", f"{config.img}:{config.tag}",
        "--label", f"org.opencontainers.image.source={source_url}",
        "--label", f"org.opencontainers.image.revision={git_commit(config)}",
        "--label", f"org.opencontainers.image.version={config.tag}",
        "app/",
    ], cwd=config.repo_root)


def push_image(config: Config) -> str:
    run(["docker", "push", f"{config.img}:{config.tag}"])
    inspected = run(
        ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", f"{config.img}:{config.tag}"],
        capture=True,
    )
    digest = inspected.stdout.strip()
    config.digest_file.write_text(digest + "\n")
    print(f"  digest capturé : {digest}")
    return digest


def export_image_archive(config: Config) -> Path:
    """Exporte l'image en archive OCI locale — source hors-ligne pour syft/grype."""
    archive = config.local_dir / "image.tar"
    run(["docker", "save", f"{config.img}:{config.tag}", "-o", str(archive)])
    return archive


def print_login_hint(config: Config) -> None:
    print(f"  echo $GITHUB_TOKEN | docker login ghcr.io -u {config.ghcr_user} --password-stdin")


def print_public_hint(config: Config) -> None:
    print("  La visibilité d'un package GHCR se règle dans l'UI GitHub (pas d'API REST) :")
    print(f"  → https://github.com/users/{config.ghcr_user}/packages/container/{GHCR_PACKAGE}/settings")
    print("    Danger Zone → Change visibility → Public.")
