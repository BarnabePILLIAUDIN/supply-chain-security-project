"""Vérification des garanties : signature + attestation de provenance + arbre des artefacts."""
from .config import Config
from .shell import cosign_env, read_digest, run


def verify_artifacts(config: Config) -> None:
    digest = read_digest(config)
    print("== cosign verify ==")
    run([config.cosign, "verify", "--key", str(config.cosign_pub), digest], extra_env=cosign_env(config))
    print("== verify-attestation (slsaprovenance) ==")
    run([config.cosign, "verify-attestation", "--key", str(config.cosign_pub),
         "--type", "slsaprovenance", digest], capture=True, extra_env=cosign_env(config))
    print("== cosign tree ==")
    run([config.cosign, "tree", digest], extra_env=cosign_env(config))
