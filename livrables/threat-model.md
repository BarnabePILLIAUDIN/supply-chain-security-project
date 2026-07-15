# Threat model — Chaîne d'approvisionnement logicielle

- **Groupe :** Cedric Gautier · Barnabé Pilliaudin · Magali Deslous-Paoli · **Date :** 15 juillet 2026

> Objectif : raisonner **menaces → contrôles → couverture**, et être honnête sur le résiduel.
> Chaque contrôle listé est **démontré** (voir `rapport.md` §4 : 5 attaques réellement bloquées).

## 1. Actif à protéger

L'artefact (image conteneur) qui tourne en production doit être **exactement** celui produit à
partir du code revu, par notre chaîne, sans altération. Propriétés visées : **intégrité**,
**authenticité** (signé par *notre* identité), **traçabilité** (provenance).

## 2. Surface & acteurs de menace

- **Dépendances tierces** (amont) — ex. backdoor **XZ Utils** (2024).
- **Runner / étape de CI compromis** — ex. **SolarWinds** (2020), **Codecov** (2021).
- **Registry compromis / substitution d'image** entre le build et le déploiement.
- **Accès cluster non autorisé** : déploiement direct d'une image pirate.
- **Développeur négligent** : tag `:latest`, image non signée, registry public quelconque.

## 3. Table menaces → contrôles → couverture

| # | Menace | Vecteur | Contrôle mis en place | Démontré par | Couverture | Résiduel |
|---|---|---|---|---|---|---|
| T1 | Artefact **altéré après build** | substitution au registry | signature cosign liée au **digest** + `verifyImages` (`mutateDigest`) | Attaque 2 (`no signatures found`) | **Forte** | le build lui-même |
| T2 | **Déploiement non autorisé** d'une image inconnue | accès au cluster | admission Kyverno `Enforce` : signature requise | Attaque 1 (`no signatures found`) | **Forte** | RBAC cluster à durcir |
| T3 | **Dépendance vulnérable** connue | amont | SBOM (Syft) + gate Grype (`--fail-on high`, `--only-fixed`) | Lab 1.4 (Flask 2.0.1, grype code=2) | **Moyenne** | 0-day / non corrigeable |
| T4 | **Origine inconnue** (pas de traçabilité) | absence de provenance | attestation de **provenance** SLSA exigée à l'admission | Attaque 5 (`no matching attestations`) | **Forte** | provenance déclarative (build non isolé) |
| T5 | **Substitution silencieuse** via tag mutable | `:latest` | interdiction `:latest` + déploiement **par digest** | Attaque 4 (`MANIFEST_UNKNOWN`) | **Forte** | — |
| T6 | **Registry pirate / typosquat** | image externe | politique `allowed-registries` (ghcr.io/notre-user seul) | Attaque 3 (`seules les images de ghcr.io/… autorisées`) | **Forte** | — |
| T7 | **CI / runner compromis** | action tierce ou étape CI malveillante | signature **keyless** liée à l'identité du workflow (Rekor) + **auto-vérification** du pipeline (`cosign verify` en fin de run) + **Dependabot** (Actions & deps à jour) + permissions **moindre privilège** | workflows `supply-chain.yml` / `ci.yml` + `dependabot.yml` (référence) | **Moyenne** | build non isolé (L3), mainteneur malveillant |

**Défense en profondeur constatée :** une image `:latest` (T5) est en pratique refusée
**d'abord** par la couche signature (elle n'existe pas / n'est pas signée), avant que
`disallow-latest-tag` ne s'exprime. Les contrôles se recouvrent volontairement.

**Isolation des contrôles constatée :** l'attaque 5 (image **signée** mais **sans provenance**)
n'est bloquée que par `require-provenance-attestation` — preuve que ce contrôle agit
indépendamment de la vérification de signature.

## 4. Ce qui reste hors périmètre / non couvert

- **Compromission du build** lui-même (nécessite SLSA L3 : build isolé, éphémère, non
  contournable). En local, la provenance est **auto-générée** → faible garantie.
- **Sécurité du poste développeur** et des **secrets** en amont (PAT GHCR, clé cosign).
- **RBAC / accès admin** au cluster : Kyverno bloque une mauvaise image, pas un admin légitime.
- Vulnérabilités **0-day** ou **sans correctif** disponible (T3 : couverture moyenne).

## 5. Niveau SLSA visé vs atteint

| | Visé | Atteint | Justification |
|---|---|---|---|
| Provenance existe (L1) | ✅ | ✅ | attestation `slsaprovenance` attachée et vérifiable (`cosign verify-attestation`) |
| Build hébergé + provenance signée (L2) | ✅ | 🟡 **partiel** | atteint **en CI** (GitHub Actions, keyless OIDC = identité du workflow) ; **pas** en local (build sur poste dev, provenance déclarative) |
| Build isolé infalsifiable (L3) | — | ✗ | hors périmètre : nécessiterait `slsa-github-generator` + séparation build/signature |

**Conclusion honnête :** notre POC garantit fortement **intégrité, authenticité et
non-déploiement de l'inconnu** (T1, T2, T5, T6 démontrés). La **traçabilité** (T4) est présente
mais reste **déclarative** hors CI : c'est le principal point contournable, et la marche vers
SLSA L3 en est la réponse.
