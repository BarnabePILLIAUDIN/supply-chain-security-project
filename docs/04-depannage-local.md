# 04 — Dépannage : faire tourner la chaîne en local (voie k3d + cosign par clé)

> Ce document liste les **pièges réels** rencontrés en montant la démo de bout en bout
> (build → sign → attest → admission Kyverno → blocage). Chaque piège a un symptôme précis
> et un correctif. L'orchestrateur `./scs.py` applique déjà ces correctifs ;
> ce doc explique **pourquoi**, utile si vous faites les labs à la main.

## Démarrage rapide (tout automatisé)

```bash
# 1) Outils : cosign 2.x IMPÉRATIF (voir §1), + syft grype k3d kubectl jq
# 2) User GHCR + connexion registry (PAT write:packages) :
export GHCR_USER=<votre-user>                                   # sinon $USER (login shell)
gh auth refresh -h github.com -s write:packages,read:packages   # ou un PAT classic
gh auth token | docker login ghcr.io -u "$GHCR_USER" --password-stdin

export COSIGN_PASSWORD=""
./scs.py all --host-port 8080 --cosign ./cosign2
# → rendre le package GHCR public (une fois) : UI GitHub, cf. §4
./scs.py attacks   --cosign ./cosign2   # démo de blocage
./scs.py verify    --cosign ./cosign2
./scs.py clean                          # supprime le cluster + .local/
```

---

## §1 — cosign 3.x n'est PAS compatible avec Kyverno 1.18 → utilisez cosign 2.x

**Symptôme :** l'image est signée (`cosign verify` OK en local), mais Kyverno refuse avec
`failed to verify image ... : no signatures found`.

**Cause :** **cosign 3.x** stocke signatures/attestations via l'**OCI 1.1 referrers API**
(format *bundle* sigstore). Le vérificateur embarqué de **Kyverno 1.18** cherche l'ancien
schéma **par tag** (`sha256-<digest>.sig` / `.att`) et ne trouve donc rien.
`--registry-referrers-mode=legacy` **ne suffit pas** : cosign 3.x écrit quand même en referrers.

**Correctif :** signer/attester avec **cosign 2.x** (≥ 2.2), qui écrit le tag `.sig`/`.att`
attendu. Homebrew installe la 3.x ; récupérez un binaire 2.x :

```bash
curl -sSfL https://github.com/sigstore/cosign/releases/download/v2.6.3/cosign-darwin-arm64 \
  -o cosign2 && chmod +x cosign2
# puis : ./scs.py sign --cosign ./cosign2 && ./scs.py attest --cosign ./cosign2
```

Vérifier le schéma écrit : `cosign triangulate <digest>` doit renvoyer `...sha256-<...>.sig`.

## §2 — L'attestation SBOM doit faire < 2 Mio (limite de contexte Kyverno)

**Symptôme :** la politique de **provenance** échoue avec
`context size limit exceeded: N bytes exceeds limit of 2097152 bytes`.

**Cause :** un SBOM SPDX **complet** (avec la section `files`) d'une image `python:3.12-slim`
pèse ~2,3 Mio, surtout à cause des ~2700 entrées de fichiers. Kyverno charge **chaque** couche
d'attestation du bundle `.att` en mémoire pour filtrer par type, et impose une limite **codée
en dur de 2 Mio par contexte** (indépendante du flag `--maxAPICallResponseLength`).

**Correctif :** attester un SBOM **au niveau paquets** (sans les fichiers) — reste un SBOM
valide, ~300 Kio, avec les 113 paquets (Python, Flask, gunicorn, libs deb) :

```bash
jq 'del(.files) | .relationships |= map(select(
  (.spdxElementId|startswith("SPDXRef-File-")|not) and
  (.relatedSpdxElement|startswith("SPDXRef-File-")|not)))' \
  sbom.spdx.json > sbom.att.spdx.json
cosign attest --key cosign.key --predicate sbom.att.spdx.json --type spdxjson <digest>
```

> `./scs.py attest` fait ce filtrage automatiquement. Le SBOM **complet** reste généré
> (`./scs.py sbom`) pour l'inspection et le scan (Lab 1).

**⚠️ Attestations non supprimables sur GHCR :** `cosign clean` échoue (`DELETE ... UNSUPPORTED`).
Si vous avez déjà attaché un gros SBOM à un digest, il y reste. Repartez d'un **nouveau digest**
(rebuild) plutôt que d'essayer de nettoyer.

## §3 — `USER` numérique dans le Dockerfile (sinon `runAsNonRoot` bloque)

**Symptôme :** admission OK, mais le pod ne démarre pas :
`container has runAsNonRoot and image has non-numeric user (appuser), cannot verify user is non-root`.

**Cause :** le manifeste impose `securityContext.runAsNonRoot: true`. Avec `USER appuser`
(un **nom**), Kubernetes ne peut pas prouver que l'UID n'est pas 0 → refus au démarrage.

**Correctif :** dans le `Dockerfile`, utiliser l'**UID numérique** (déjà appliqué) :

```dockerfile
RUN useradd --create-home --uid 10001 appuser
USER 10001          # et non 'USER appuser'
```

## §4 — Le package GHCR doit être *public* (ou fournir un imagePullSecret)

**Symptôme :** le cluster ne peut pas tirer l'image / ses signatures (`DENIED`, `access denied`).

**Cause :** un package GHCR est **privé** par défaut ; Kyverno (dans le cluster) doit lire
l'image **et** les artefacts cosign (`.sig`, `.att`).

**Correctif :** rendre le package public (pas d'API REST — passez par l'UI) :
`https://github.com/users/<votre-user>/packages/container/scs-demo-app/settings`
→ *Danger Zone* → *Change visibility* → **Public**.
Sinon : créer un secret `docker-registry` dans le namespace `app` et le référencer.

## §5 — `readOnlyRootFilesystem` : monter un `/tmp` inscriptible

**Symptôme :** `CrashLoopBackOff`, logs gunicorn :
`FileNotFoundError: No usable temporary directory found in ['/tmp', ...]`.

**Cause :** `readOnlyRootFilesystem: true` rend `/` non inscriptible ; gunicorn écrit des
fichiers temporaires de worker dans `/tmp`.

**Correctif :** monter un `emptyDir` sur `/tmp` (déjà dans `k8s/deployment.yaml`) :

```yaml
          volumeMounts:
            - { name: tmp, mountPath: /tmp }
      volumes:
        - { name: tmp, emptyDir: {} }
```

## §6 — Conflit de port hôte (k3d)

**Symptôme :** `Bind for 0.0.0.0:8080 failed: port is already allocated`.

**Cause :** un autre service occupe déjà le port 8080 de l'hôte.

**Correctif :** choisir un autre port hôte — `./scs.py` expose `--host-port` :

```bash
./scs.py cluster --host-port 18080      # l'app sera sur http://localhost:18080
```

## §8 — Installer Kyverno : `kubectl apply --server-side` (CRD trop grosses)

**Symptôme :** `kubectl apply -f .../install.yaml` échoue avec
`CustomResourceDefinition ... metadata.annotations: Too long: may not be more than 262144 bytes`
(souvent en **ré-exécution**, quand Kyverno est déjà installé).

**Cause :** les CRD Kyverno dépassent la limite d'annotation du **client-side apply**
(qui stocke `last-applied-configuration`). Un `kubectl create` marche à froid mais échoue
si l'objet existe déjà, et le repli en `apply` échoue alors sur cette limite.

**Correctif :** installer en **server-side apply**, idempotent et sans annotation géante :

```bash
kubectl apply --server-side --force-conflicts -f \
  https://github.com/kyverno/kyverno/releases/latest/download/install.yaml
```

(Déjà appliqué par `./scs.py kyverno`.)

## §7 — Quel contrôle bloque `:latest` ?

En pratique, une image `:latest` correspondant au motif `verifyImages` est refusée **d'abord**
par le webhook de **vérification de signature** (elle n'existe pas / n'est pas signée), avant
que le message de `disallow-latest-tag` n'apparaisse. Le tag est bien bloqué — simplement par
la couche signature. Plusieurs politiques se recouvrent : c'est la défense en profondeur.
