"""Rendu des templates pédagogiques vers .local/ — jamais modifiés en place.

Injecte le user GHCR, le contenu de cosign.pub (indentation préservée) et le digest signé.
"""
from .config import Config
from .shell import read_digest


def render_manifests(config: Config) -> None:
    if not config.cosign_pub.exists():
        raise RuntimeError(f"{config.cosign_pub} absent — lancez 'keygen' d'abord.")
    public_key = config.cosign_pub.read_text()
    digest_sha = read_digest(config).split("@")[-1]

    for template in sorted((config.repo_root / "policies" / "kyverno").glob("*.yaml")):
        with_user = template.read_text().replace("${GHCR_USER}", config.ghcr_user)
        (config.local_dir / template.name).write_text(_inject_public_key(with_user, public_key))

    deployment = (config.repo_root / "k8s" / "deployment.yaml").read_text()
    deployment = deployment.replace("${GHCR_USER}", config.ghcr_user)
    deployment = deployment.replace("@sha256:REMPLACEZ_PAR_VOTRE_DIGEST", f"@{digest_sha}")
    (config.local_dir / "deployment.yaml").write_text(deployment)
    print(f"  ✓ manifests rendus vers {config.local_dir}/ (user={config.ghcr_user}, {digest_sha})")


def _inject_public_key(template: str, public_key_pem: str) -> str:
    """Remplace le bloc PEM placeholder par le vrai cosign.pub, en reprenant l'indentation
    de la ligne '-----BEGIN PUBLIC KEY-----' (elle diffère entre les politiques)."""
    pem_lines = public_key_pem.strip().splitlines()
    output, lines, index = [], template.splitlines(), 0
    while index < len(lines):
        line = lines[index]
        if "-----BEGIN PUBLIC KEY-----" in line:
            indent = line[: len(line) - len(line.lstrip())]
            output.extend(indent + pem_line for pem_line in pem_lines)
            index += 1
            while index < len(lines) and "-----END PUBLIC KEY-----" not in lines[index]:
                index += 1
            index += 1  # saute la ligne END
            continue
        output.append(line)
        index += 1
    return "\n".join(output) + "\n"
