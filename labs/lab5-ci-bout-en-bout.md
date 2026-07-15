# Lab 5 (bonus) — Tout enchaîner en CI GitHub Actions (~1 h 30)

**But :** automatiser toute la chaîne dans un workflow. C'est ce qui vous fait réellement
progresser vers **SLSA L2** : le build a lieu sur une **plateforme hébergée**, l'identité de
signature est celle du **workflow** (OIDC), et rien n'est fait à la main.

> Un workflow de référence complet est fourni : [`../.github/workflows/supply-chain.yml`](../.github/workflows/supply-chain.yml).
> Lisez-le, adaptez-le, activez-le sur votre fork.

## Différence clé avec les labs 0→4 : keyless

Aux labs 2–4, vous signiez **par clé** (`cosign.key` local + `cosign.pub` dans la politique).
Ici, la CI signe **keyless** : pas de clé stockée, l'identité est
`https://github.com/<user>/<repo>/.github/workflows/supply-chain.yml@refs/heads/main`.
La politique d'admission n'exige donc plus une clé, mais **cette identité de workflow**.

> ⚠️ **Deux pièges hérités des labs locaux s'appliquent aussi en CI** — le workflow de
> référence les corrige déjà, ne les réintroduisez pas :
> - **cosign 2.x**, pas 3.x (la 3.x écrit via l'OCI referrers API, illisible par Kyverno 1.18).
>   Le workflow épingle `cosign-release: v2.6.3`. Cf. [`../docs/04-depannage-local.md`](../docs/04-depannage-local.md) §1.
> - **SBOM allégé** (`del(.files)`) pour l'attestation : le SBOM complet dépasse la limite de
>   contexte de 2 Mio de Kyverno. Cf. `docs/04` §2.

## 5.1 Ce que fait le pipeline

À chaque `push` sur `main`, le workflow :

1. **build** l'image (par digest, sorti par `docker/build-push-action`) ;
2. **pousse** l'image sur GHCR ;
3. génère le **SBOM** complet (Syft) ;
4. **scanne** (Grype) et **casse** si `CRITICAL` corrigeable ;
5. installe **cosign 2.x** puis **signe** l'image en **keyless** (OIDC du runner) ;
6. **attache** l'attestation **SBOM allégée** (`cosign attest --type spdxjson`) ;
7. **attache** l'attestation de **provenance** (`--type slsaprovenance`) ;
8. **vérifie sa propre sortie** : `cosign verify` + `verify-attestation` contre l'**identité du
   workflow** (keyless). Le pipeline échoue s'il ne peut pas prouver ce qu'il vient de produire.

Aucune clé privée n'est stockée. Le workflow déclare le **moindre privilège**
(`contents: read`, `packages: write`, `id-token: write`) et une clé `concurrency` qui sérialise
les runs sans couper une signature en cours.

> **Seule `main` produit une image déployable.** Défense en profondeur sur deux niveaux :
> le job ne build/signe **que si `github.ref == refs/heads/main`** (un `workflow_dispatch` sur une
> autre branche ne fait rien), et **à l'admission** Kyverno exige le subject
> `…/supply-chain.yml@refs/heads/main`. Une image signée depuis une autre branche porte
> `@refs/heads/<branche>` dans son identité → **refusée au déploiement**.

## 5.1bis — CI du code + hygiène des dépendances

Deux fichiers complètent la chaîne (indépendants du build/sign) :

- [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml) — à **chaque push/PR**, sans
  secret : `pytest` sur l'app, compilation du package `supplychain/`, smoke test de la CLI, et un
  **garde-fou** qui échoue si un user GHCR est codé en dur (le projet impose `${GHCR_USER}`).
- [`../.github/dependabot.yml`](../.github/dependabot.yml) — met à jour chaque semaine les
  **GitHub Actions** et les **dépendances Python** : les actions et les libs sont elles-mêmes des
  dépendances tierces (menace T2 du threat model). C'est de l'hygiène supply-chain sur *notre*
  propre chaîne.

## 5.2 Activer le workflow sur votre fork

```bash
# 1) Le workflow est déjà dans .github/workflows/supply-chain.yml : il suffit de pousser sur main.
git push origin main            # ou onglet Actions → "supply-chain" → Run workflow

# 2) Permissions : déjà déclarées dans le workflow (aucun secret à créer,
#    GITHUB_TOKEN suffit) :
#      contents: read | packages: write | id-token: write   (OIDC keyless)

# 3) UNE fois : rendre le package GHCR public (cf. docs/04 §4) pour que le cluster
#    puisse lire l'image ET ses artefacts cosign (.sig/.att).
```

## 5.3 Adapter la vérification Kyverno au mode keyless

En keyless, la politique de signature doit exiger **l'identité du workflow**, pas une clé.
Une variante prête à l'emploi est fournie :
[`../policies/kyverno/03-verify-signature-keyless.yaml`](../policies/kyverno/03-verify-signature-keyless.yaml)
(`${GHCR_USER}` est substitué au rendu, comme les autres politiques).

Elle **remplace** la politique par clé (même nom `verify-image-signature`, même image ciblée) —
ne les cumulez pas, sinon il faudrait les **deux** signatures :

```bash
export GHCR_USER=<votre-user>
./scs.py render                                        # rend .local/ (dont la variante keyless)

kubectl delete -f .local/03-verify-signature.yaml      # retire la politique PAR CLÉ
kubectl apply  -f .local/03-verify-signature-keyless.yaml   # applique la politique KEYLESS
kubectl get clusterpolicy                              # verify-image-signature : Ready true
```

Extrait de la variante keyless :

```yaml
attestors:
  - count: 1
    entries:
      - keyless:
          issuer: "https://token.actions.githubusercontent.com"
          subject: "https://github.com/${GHCR_USER}/supply-chain-security-project/.github/workflows/supply-chain.yml@refs/heads/main"
          rekor:
            url: "https://rekor.sigstore.dev"
```

> **C'est le vrai zero-trust :** le cluster n'accepte que ce qui a été signé **par ce workflow
> précis, sur cette branche précise**. Un attaquant qui pousse une image ne peut pas se faire
> passer pour ce workflow (il n'a pas l'OIDC du runner GitHub).

## 5.4 Vérifier de bout en bout

```bash
# Digest produit par la CI : onglet Actions → étape "Récapitulatif", ou :
#   crane digest ghcr.io/<user>/scs-demo-app:<sha>
cosign verify \
  --certificate-identity "https://github.com/<user>/supply-chain-security-project/.github/workflows/supply-chain.yml@refs/heads/main" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/<user>/scs-demo-app@sha256:...
```

Déployez ce digest CI-signé sur le cluster (via `.local/deployment.yaml`, digest à jour) ⇒
**accepté** ✅. Poussez quoi que ce soit d'autre (non signé, ou signé par une autre identité)
⇒ **refusé** ❌.

## ✅ Critères de sortie du lab

- [ ] Le workflow build + push + SBOM + scan + sign + attest passe au vert.
- [ ] Le workflow signe avec **cosign 2.x** et atteste un **SBOM allégé** (pas de régression §1/§2).
- [ ] `cosign verify` réussit avec l'**identité du workflow** (keyless).
- [ ] La politique Kyverno **keyless** accepte l'image CI et **refuse** le reste.
- [ ] Vous savez expliquer **pourquoi c'est SLSA ~L2** et ce qui manque pour **L3**.

---

## Discussion pour le rapport : SLSA L2 vs L3

| | Vous avez (L2-ish) | Il faudrait pour L3 |
|---|---|---|
| Build | Hébergé (GitHub Actions) | Build **isolé/éphémère** non contournable, paramètres non falsifiables |
| Provenance | Signée par l'OIDC du runner | Générée par un **générateur isolé** (ex. `slsa-github-generator` en mode L3) |
| Falsifiabilité | Un mainteneur avec droits peut altérer le workflow | Séparation stricte, revue obligatoire, provenance **infalsifiable** |

Soyez **honnêtes** dans le rapport : indiquez le niveau réellement atteint et ce qui reste contournable.
