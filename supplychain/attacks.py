"""Lab 4 — rejouer les 5 scénarios d'attaque ; chacun DOIT être refusé par Kyverno."""
import shlex
import subprocess

from .config import Config
from .shell import copy_app_to_temp_context, cosign_env, run

ATTACK_POD_NAMES = ["pirate", "tampered", "fromdockerhub", "uselatest", "noprov"]


def run_attacks(config: Config) -> None:
    print(f"=== Scénarios attaque/défense (namespace {config.namespace}) ===")
    try:
        unsigned = _build_variant(config, "unsigned", "unsigned")
        _expect_denied(config, "Attaque 1 — image NON signée",
                       ["kubectl", "run", "pirate", f"--image={unsigned}", "-n", config.namespace])

        tampered = _build_variant(config, "tampered", "backdoor-simulee")
        _expect_denied(config, "Attaque 2 — image ALTÉRÉE après signature (digest changé)",
                       ["kubectl", "run", "tampered", f"--image={tampered}", "-n", config.namespace])

        _expect_denied(config, "Attaque 3 — registry non autorisé (docker.io)",
                       ["kubectl", "run", "fromdockerhub", "--image=nginx:1.27", "-n", config.namespace])

        _expect_denied(config, "Attaque 4 — tag :latest interdit",
                       ["kubectl", "run", "uselatest", f"--image={config.img}:latest", "-n", config.namespace])

        no_provenance = _build_variant(config, "noprov", "sans-provenance")
        print(f"  (on SIGNE {config.img}:noprov mais on n'attache AUCUNE provenance)")
        run([config.cosign, "sign", "--key", str(config.cosign_key), "--yes", no_provenance],
            capture=True, extra_env=cosign_env(config))
        _expect_denied(config, "Attaque 5 — signée mais SANS attestation de provenance",
                       ["kubectl", "run", "noprov", f"--image={no_provenance}", "-n", config.namespace])
        print("\n=== Fin des scénarios (5/5) ===")
    finally:
        _cleanup_attack_pods(config)


def _build_variant(config: Config, tag: str, label: str) -> str:
    """Construit une variante au contenu modifié (label distinctif → nouveau digest), la pousse,
    et renvoie sa référence par digest."""
    context = copy_app_to_temp_context(config, f"attack-{tag}")
    run(["docker", "build", "-q", "-t", f"{config.img}:{tag}", "--label", f"scs.demo={label}", str(context)])
    run(["docker", "push", f"{config.img}:{tag}"], capture=True)
    inspected = run(["docker", "inspect", "--format", "{{index .RepoDigests 0}}", f"{config.img}:{tag}"], capture=True)
    return inspected.stdout.strip()


def _expect_denied(config: Config, title: str, cmd) -> None:
    print("\n" + "━" * 61)
    print(f"▶ {title}")
    print(f"  $ {' '.join(shlex.quote(part) for part in cmd)}")
    result = subprocess.run(cmd, text=True, capture_output=True)
    for line in (result.stdout + result.stderr).splitlines():
        print(f"    {line}")
    if result.returncode != 0:
        print(f"  ✅ BLOQUÉ (code={result.returncode}) — comportement attendu.")
    else:
        print("  ❌ ACCEPTÉ — la politique n'a PAS bloqué (à investiguer).")


def _cleanup_attack_pods(config: Config) -> None:
    subprocess.run(
        ["kubectl", "delete", "pod", "-n", config.namespace, *ATTACK_POD_NAMES, "--ignore-not-found"],
        capture_output=True, text=True,
    )
