# 05 — Rapport de vérification : lancement local de bout en bout

> **Objet.** Prouver que toute la chaîne d'approvisionnement (SBOM → scan → signature →
> attestations → admission Kyverno → blocage) **tourne en local** et que **chaque garantie
> est vérifiable par une commande**. Ce document liste, pour chaque résultat attendu, la
> **commande de vérification** et le **résultat attendu**.
>
> **Environnement de référence.** macOS (Apple Silicon) · Docker/OrbStack · k3d 5.9 ·
> kubectl 1.36 · syft 1.46 · grype 0.115 · **cosign 2.6.3** · Kyverno 1.18.
> **Choix retenus.** Registry **GHCR** + signature **par clé** · cluster **k3d** ·
> host-port **18080** (8080 occupé sur la machine de test).
>
> ⚠️ **cosign 2.x obligatoire** (la 3.x écrit via l'OCI referrers API, illisible par Kyverno 1.18 —
> cf. [`04-depannage-local.md`](04-depannage-local.md) §1). Binaire fourni en local : `./cosign2`.

## 0. Prérequis à la vérification

```bash
# depuis la racine du dépôt, une fois :
export GHCR_USER=<votre-user>    # user GHCR ; sinon $USER (login shell) est pris. Aucun défaut codé en dur.
gh auth refresh -h github.com -s write:packages,read:packages   # ou un PAT classic write:packages
gh auth token | docker login ghcr.io -u "$GHCR_USER" --password-stdin
# le package GHCR scs-demo-app doit être PUBLIC (UI GitHub, cf. §4 dépannage)
export COSIGN_PASSWORD=""        # la clé de démo est sans mot de passe
```

> **User GHCR** — résolu partout dans l'ordre **`--user` > `$GHCR_USER` > `$USER`**. Il n'y a
> **aucun nom codé en dur** : sans valeur, l'outil s'arrête avec un message clair. Les manifests
> utilisent la variable **`${GHCR_USER}`**, substituée au rendu vers `.local/`.

Les commandes ci-dessous supposent le cluster monté et l'app déployée. Pour tout reconstruire
depuis zéro (avec `GHCR_USER` exporté) : `./scs.py all --host-port 18080 --cosign ./cosign2` (cf. §7).

---

## 1. Récapitulatif (demande → livré → vérifié)

| # | Demandé | Livré | Vérifié |
|---|---|---|---|
| 1 | Lire les `.md` et le « à faire » | Analyse du sujet + des 5 labs | — (informatif) |
| 2 | Découvrir/analyser/**plan** de lancement local | Plan validé (dry-run + automatisation) | ✅ |
| 3 | **Lancer tout en local** | Chaîne complète labs 0→4 exécutée | ✅ §3–§4 |
| 4 | Vérifier que **tout est fait** (labs) | Écarts techniques comblés (Lab 1.4, attaques 2 & 5) | ✅ §4 |
| 5 | **Scripter en Python** (au lieu de Make) | `scs.py` (stdlib) équivalent complet | ✅ §3 |
| 6 | S'assurer que **tout marche** | Cycle `clean → all → attacks → verify` à zéro ; bugs trouvés & corrigés (cf. §5) | ✅ §3 |
| 7 | **Scaffolding plus propre** | `scs.py` éclaté en package `supplychain/` (1 module par responsabilité) | ✅ §7 |
| 8 | Env var **`USER`** exportable | Résolution `--user > $GHCR_USER > $USER` (Python, bash, Make) | ✅ §0 |
| 9 | **Variabiliser** les politiques, aucun nom codé en dur | Token `${GHCR_USER}` dans les manifests ; `cedricgautier` retiré du code | ✅ §0/§7 |

**Réalisé au-delà du local :** Lab 5 **CI/CD** (`.github/workflows/{supply-chain,ci}.yml`),
signature **keyless** en CI (+ politique `03-verify-signature-keyless.yaml`), **Dependabot**,
et livrables **rapport** + **threat model** remplis avec sorties réelles.
**Hors périmètre restant :** SBOM CycloneDX, vidéo de démo. Détail en §6.

---

## 2. Outillage installé

```bash
for t in docker k3d kubectl syft grype jq; do printf "%-8s " "$t"; \
  ($t version 2>/dev/null || $t --version 2>/dev/null) | head -1; done
./cosign2 version | grep -i gitversion
```

**Attendu.** Chaque outil répond ; `cosign2` = `GitVersion: v2.6.3` (branche 2.x).

Équivalent scripté : `./scs.py tools --cosign ./cosign2` → une ligne `✓` par binaire.

---

## 3. Lancement en une commande (`scs.py`)

```bash
# Chaîne complète : build → push → sbom → scan → keygen → sign → attest
#                   → cluster → kyverno → policies → deploy → status
export GHCR_USER=<votre-user> COSIGN_PASSWORD=""
./scs.py all --host-port 18080 --cosign ./cosign2
```

**Attendu (fin de sortie).**
```
deployment "scs-demo-app" successfully rolled out
...
scs-demo-app-...   1/1   Running
scs-demo-app-...   1/1   Running
✅ Chaîne complète OK. Lancez 'attacks' pour la démo de blocage.
```

> **Résultat clé prouvé :** le déploiement est **accepté sur un cluster neuf sans aucun
> patch Kyverno** — l'attestation SBOM réduite aux paquets (< 2 Mio) suffit. Le cycle
> `clean → all` a été rejoué intégralement pour le démontrer (et a permis de détecter puis
> corriger un bug `NameError` dans `create_cluster`).

Sous-commandes `./scs.py` (une par étape des labs) :

| `./scs.py <cmd>` | Rôle |
|---|---|
| `tools` | vérifie les binaires |
| `build` / `push` | build (labels OCI) · push + capture digest |
| `sbom` / `scan` / `scan-vuln` | SBOM SPDX · gate Grype · démo Lab 1.4 |
| `keygen` `sign` `attest` `clean-sigs` | clé · signer · attester (SBOM+provenance) |
| `render` | rend policies+deployment vers `.local/` |
| `cluster` `kyverno` `policies` `deploy` `status` | k3d · Kyverno · politiques · déploiement |
| `attacks` `verify` `clean` `all` | démo blocage · preuves cosign · nettoyage · tout |

---

## 4. Vérification pas à pas (par lab)

### Lab 0 — Image & registry

```bash
docker build -t ghcr.io/<votre-user>/scs-demo-app:0.1.0 app/     # ./scs.py build
docker run --rm -d -p 8080:8080 --name scs ghcr.io/<votre-user>/scs-demo-app:0.1.0
curl -s localhost:8080/health ; echo ; docker stop scs
```
**Attendu.** `{"status":"ok","version":"1.0.0"}`.
Push + digest : `./scs.py push …` écrit la référence par digest dans `.local/digest`.

### Lab 1 — SBOM & scan (gate)

```bash
./scs.py sbom --user <votre-user>       # -> .local/sbom.spdx.json
./scs.py scan --user <votre-user> ; echo "code=$?"
```
**Attendu.** SBOM généré ; scan **code=0** (image saine, aucune CVE `CRITICAL` corrigeable —
la gate `.grype.yaml` ne casse que sur CRITICAL).

Démonstration « la gate casse réellement » (Lab 1.4) :
```bash
./scs.py scan-vuln --user <votre-user>
```
**Attendu.** Une CVE **Flask 2.0.1 HIGH** (`GHSA-m2qf-hxjv-5gpq`, corrigée en 2.2.5) apparaît et
`✅ CHAÎNE CASSÉE (grype code=2)`. Le `app/requirements.txt` du dépôt **reste intact**
(`grep Flask app/requirements.txt` → `Flask==3.0.3`).

### Lab 2 — Signature & attestations

```bash
./scs.py verify --cosign ./cosign2
```
**Attendu.**
- `cosign verify` : *The signatures were verified against the specified public key*.
- `verify-attestation --type slsaprovenance` : predicateType `https://slsa.dev/provenance/v0.2`.
- `cosign tree` : une entrée **🔐 Signatures** (`…​.sig`) et une entrée **💾 Attestations** (`…​.att`).
- `cosign.key` n'est jamais commité : `git check-ignore cosign.key` → renvoie `cosign.key`.

### Lab 3 — Cluster + admission (image légitime ACCEPTÉE)

```bash
kubectl get clusterpolicy
kubectl get pods -n app
curl -s localhost:18080/health ; echo      # host-port du run de référence
```
**Attendu.** 4 `ClusterPolicy` `READY=True` (`allowed-registries`, `disallow-latest-tag`,
`verify-image-signature`, `require-provenance-attestation`) ; 2 pods `scs-demo-app` **Running** ;
`/health` → `{"status":"ok","version":"1.0.0"}`.

### Lab 4 — Attaque / défense (tout REFUSÉ)

```bash
COSIGN_PASSWORD="" ./scs.py attacks --user <votre-user> --cosign ./cosign2
```
**Attendu — 5 scénarios, tous `✅ BLOQUÉ (code=1)` :**

| Attaque | Politique qui bloque | Menace |
|---|---|---|
| 1 — image non signée | `verify-image-signature` (+ provenance) | artefact non autorisé |
| 2 — image altérée après signature | signature liée au **digest** | **SolarWinds** |
| 3 — registry non autorisé (`nginx`) | `allowed-registries` | registry pirate / typosquatting |
| 4 — tag `:latest` | signature (l'image `:latest` n'existe/n'est pas signée) | substitution sous tag mutable |
| 5 — signée mais **sans provenance** | `require-provenance-attestation` **seule** | origine non prouvée |

> L'attaque 5 est la preuve d'isolation : seule la politique de **provenance** refuse
> (la signature, elle, passe) → « signer ne suffit pas, il faut prouver l'origine ».

---

## 5. Blocages rencontrés & correctifs (tous appliqués)

| # | Symptôme | Cause | Correctif |
|---|---|---|---|
| 1 | Kyverno : `no signatures found` alors que `cosign verify` OK | cosign 3.x = OCI referrers API, illisible par Kyverno 1.18 | **cosign 2.x** (`./cosign2`), binaire configurable via `--cosign` |
| 2 | `context size limit exceeded: … 2097152` | SBOM complet (fichiers) > 2 Mio ; limite de contexte codée en dur | attester un **SBOM niveau paquets** (~300 Kio) |
| 3 | Pod refusé : `runAsNonRoot … non-numeric user (appuser)` | `USER appuser` (nom) incompatible `runAsNonRoot` | `app/Dockerfile` → **`USER 10001`** |
| 4 | Cluster ne peut pas tirer l'image / signatures | package GHCR privé par défaut | package **public** (UI GitHub) |
| 5 | `CrashLoopBackOff` : *No usable temporary directory* | `readOnlyRootFilesystem` + gunicorn écrit dans `/tmp` | `k8s/deployment.yaml` → **emptyDir sur `/tmp`** |
| 6 | k3d : `port 8080 already allocated` | port hôte occupé | `HOST_PORT` / `--host-port` configurable (18080 ici) |
| 7 | `scs.py all` : `NameError: _cluster_exists` | helper appelé mais non défini | helper `_cluster_exists` ajouté (trouvé par le run à zéro) |
| 8 | `kubectl apply` Kyverno : `annotations: Too long (>262144 o)` | CRD Kyverno trop grosses pour l'apply *client-side* (surtout en ré-exécution) | **`kubectl apply --server-side`** (idempotent) |

Détail pédagogique complet : [`04-depannage-local.md`](04-depannage-local.md) (§1–§8).

---

## 6. Extensions : état (fait / restant)

| Élément | État | Détail |
|---|---|---|
| **Lab 5 — CI/CD GitHub Actions** | ✅ **fait** | `supply-chain.yml` (build→scan→sign→attest→**verify** keyless) + `ci.yml` (pytest app + compile/smoke tooling + garde-fou user codé en dur). Pousser sur le fork pour l'exécuter. |
| Signature **keyless** (OIDC/Fulcio/Rekor) | ✅ **fournie** (CI) | `cosign sign` sans `--key` dans le workflow + politique `policies/kyverno/03-verify-signature-keyless.yaml` (identité du workflow). En **local**, on reste par clé (choix « GHCR + par clé »). |
| **Dependabot** | ✅ **fait** | `.github/dependabot.yml` : maj hebdo des GitHub Actions + deps pip (hygiène supply-chain). |
| **Rapport** (L2) + **threat model** (L3) | ✅ **faits** | `livrables/rapport.md` et `livrables/threat-model.md`, remplis avec les sorties réelles du POC. |
| SBOM **CycloneDX** | ⚪ restant | Critère Lab 1 = « SPDX **et/ou** CycloneDX » → SPDX suffit. `syft … -o cyclonedx-json` pour l'ajouter. |
| **Vidéo** de démo | ⚪ restant | Livrable étudiant (capture d'écran/vidéo) ; les **sorties texte** réelles sont dans `livrables/rapport.md` §4. |

---

## 7. Fichiers créés / modifiés

**Créés (automatisation) :** `scs.py` (point d'entrée) + package **`supplychain/`** (config, shell,
image, sbom, signing, manifests, cluster, attacks, verify, pipeline, cli) · `cluster/k3d-config.yaml` ·
`docs/04-depannage-local.md` · `docs/05-rapport-verification.md`.
**Créés (CI/CD) :** `.github/workflows/ci.yml` (tests + tooling) · `.github/dependabot.yml` ·
`policies/kyverno/03-verify-signature-keyless.yaml` · `livrables/rapport.md` · `livrables/threat-model.md`.
**Modifiés (correctifs réels + variabilisation + CI) :** `app/Dockerfile` · `k8s/deployment.yaml` ·
`policies/kyverno/{01,03,04}*.yaml` (token **`${GHCR_USER}`** au lieu de `<votre-user>`) ·
`.github/workflows/supply-chain.yml` (cosign 2.x, SBOM allégé, verify keyless, concurrency) ·
`labs/lab5-ci-bout-en-bout.md` · `.gitignore` · `README.md` · `docs/01-prerequis-setup.md` ·
`labs/lab3-cluster-admission.md`.
**Rendus vers `.local/` (gitignoré), jamais déployés depuis la source :** les 4 politiques + le
deployment, avec `${GHCR_USER}`, `cosign.pub` et le digest substitués.
**Binaire local (gitignoré, régénérable) :** `./cosign2` (cosign 2.x).

```bash
git status --short          # revue des changements (rien n'est commité)
git check-ignore .local cosign.key cosign.pub cosign2   # tous ignorés
```

---

## 8. Reproduire intégralement à zéro

```bash
export GHCR_USER=<votre-user> COSIGN_PASSWORD=""     # user résolu ; clé de démo sans mot de passe
./scs.py clean                                        # supprime cluster + .local/
./scs.py all     --host-port 18080 --cosign ./cosign2
./scs.py attacks                   --cosign ./cosign2
./scs.py verify                    --cosign ./cosign2
```

**Critère de réussite global :** `all` se termine par 2 pods `Running`, `attacks` affiche
**5/5 `✅ BLOQUÉ`**, et `/health` répond `{"status":"ok","version":"1.0.0"}`.

> Si `./cosign2` a été purgé par `clean` (il est à la racine, hors `.local/`, donc conservé),
> le retélécharger : cf. [`04-depannage-local.md`](04-depannage-local.md) §1.
