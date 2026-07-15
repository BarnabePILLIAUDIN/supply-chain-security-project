# Rapport — Chaîne d'approvisionnement logicielle sécurisée

- **Groupe :** Cedric Gautier · Barnabé Pilliaudin · Magali Deslous-Paoli
- **Fork :** https://github.com/BarnabePILLIAUDIN/supply-chain-security-project
- **Voie :** ☒ Local (k3d + cosign par clé) ☐ Azure (AKS/ACR)
- **Date :** 15 juillet 2026

> Chaque garantie annoncée ci-dessous est **prouvable par une commande** ; les sorties collées
> sont **réelles** (image `ghcr.io/cedricgautier/scs-demo-app@sha256:324266…bebf`, cluster k3d `scs`).

---

## 1. Contexte & objectif

Les attaques récentes ne visent plus l'application en production mais la **chaîne qui la
fabrique** : **SolarWinds** (2020, code malveillant injecté dans le build et signé par
l'éditeur), **Codecov** (2021, script CI exfiltrant les secrets), **XZ Utils** (2024, backdoor
introduite sur 3 ans dans une dépendance). Le risque que nous adressons : **une image qui tourne
en production peut ne pas être celle que nous avons construite à partir du code revu.**

Objectif du POC : rendre l'artefact **vérifiable de bout en bout** — intégrité, authenticité,
traçabilité — et faire en sorte que le cluster **refuse activement** toute image qu'il ne peut
pas prouver digne de confiance, au lieu de faire confiance par défaut.

## 2. Architecture de la chaîne

```
code ─► build ─► SBOM (Syft) ─► scan (Grype, gate) ─► sign (cosign 2.x) ─► attest ─► push GHCR
                                                            │  ├─ attestation SBOM (allégée)
                                                            │  └─ attestation provenance (SLSA)
                                                            ▼
        Cluster k3d + Kyverno (admission control, Enforce)
          ├─ registry autorisé ?         sinon ❌   (allowed-registries)
          ├─ pas de :latest ?            sinon ❌   (disallow-latest-tag)
          ├─ signée par NOTRE clé ?      sinon ❌   (verify-image-signature)
          └─ provenance présente ?       sinon ❌   (require-provenance-attestation)
```

| Outil | Rôle |
|---|---|
| **Syft** | génère le SBOM (inventaire des paquets) au format SPDX |
| **Grype** | scanne le SBOM/l'image, **casse le build** sur CVE corrigeable (gate) |
| **cosign 2.x** | signe l'image par clé et attache les attestations (SBOM + provenance) |
| **Kyverno** | admission webhook : *avant* création du Pod, vérifie et **refuse** |
| **k3d** | cluster Kubernetes local (k3s en conteneur) |

> **Choix cosign 2.x** (et non 3.x) : la 3.x écrit signatures et attestations via l'OCI 1.1
> *referrers API*, que le vérificateur embarqué de Kyverno 1.18 ne sait pas lire. La 2.x écrit
> l'ancien schéma par tag (`sha256-<digest>.sig` / `.att`) attendu par Kyverno.

**Deux voies d'exécution** partagent la même chaîne :

- **Locale** — l'orchestrateur `scs.py` (par clé, cluster k3d) : c'est le POC démontré ici.
- **CI/CD** (`.github/workflows/`) — `supply-chain.yml` rejoue build→scan→sign→attest en
  **keyless** (identité OIDC du workflow) puis **vérifie sa propre sortie**
  (`cosign verify` + `verify-attestation`) ; `ci.yml` valide le code à chaque PR (pytest sur
  l'app, compilation du package, garde-fou « aucun user codé en dur ») ; **Dependabot** met à
  jour les Actions et les dépendances Python (les Actions sont elles-mêmes des dépendances — cf.
  threat model T2).

## 3. Mise en œuvre

Toute la chaîne est automatisée par un orchestrateur Python maison (`scs.py` + package
`supplychain/`, stdlib uniquement). Aucun nom d'utilisateur n'est codé en dur : résolution
`--user > $GHCR_USER > $USER`. Les politiques et manifestes sont **variabilisés** (`${GHCR_USER}`)
et rendus vers `.local/` (les templates pédagogiques ne sont jamais modifiés en place).

### 3.1 SBOM (Syft, format SPDX)

```
$ syft docker-archive:.local/image.tar -o spdx-json > .local/sbom.spdx.json
  → SBOM SPDX : 2,2 Mio, 113 paquets (Python, Flask, gunicorn, libs Debian)
```

Le SBOM **complet** (2,2 Mio, avec la section `files`) sert à l'inspection et au scan. Pour
l'**attestation**, on atteste une vue **au niveau paquets** (`del(.files)`, ~300 Kio) : Kyverno
impose une limite de contexte codée en dur de **2 Mio** par attestation, qu'un SBOM complet
dépasse (voir §5, limites).

### 3.2 Scan (Grype) — la gate qui casse

Politique `.grype.yaml` : échec sur vulnérabilité **corrigeable**. Sur l'image saine
(Flask 3.0.3), aucune CVE bloquante — la gate **passe** (Low/Medium seulement) :

```
flask   3.0.3  3.1.3    python  GHSA-68rp-wp8r-4726  Low
python  3.12   …        binary  CVE-2025-13837       Medium
# → pas de HIGH/CRITICAL corrigeable : build OK
```

Démonstration **Lab 1.4** — on épingle volontairement Flask à **2.0.1** (le `requirements.txt`
du dépôt reste intact) et la gate **casse** :

```
$ grype docker-archive:.local/vuln.tar --only-fixed --fail-on high
  NAME   INSTALLED  FIXED IN  TYPE    VULNERABILITY        SEVERITY
  flask  2.0.1      2.2.5     python  GHSA-m2qf-hxjv-5gpq  High
  ✅ CHAÎNE CASSÉE (grype code=2) — CVE Flask HIGH corrigeable.
```

### 3.3 Signature (cosign, par clé) — preuve

```
$ cosign verify --key cosign.pub ghcr.io/cedricgautier/scs-demo-app@sha256:324266…bebf

Verification for ghcr.io/cedricgautier/scs-demo-app@sha256:324266…bebf --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - Existence of the claims in the transparency log was verified offline
  - The signatures were verified against the specified public key
```

`cosign tree` montre les artefacts rattachés à l'image (schéma par tag lisible par Kyverno) :

```
📦 ghcr.io/cedricgautier/scs-demo-app@sha256:324266…bebf
├── 💾 Attestations : …:sha256-324266…bebf.att   (14 couches : SBOM + provenance)
└── 🔐 Signatures   : …:sha256-324266…bebf.sig
```

### 3.4 Attestations (SBOM + provenance) — preuve

```
$ cosign verify-attestation --key cosign.pub --type spdxjson       …@sha256:324266…bebf  → OK
$ cosign verify-attestation --key cosign.pub --type slsaprovenance …@sha256:324266…bebf  → OK
  (mêmes 4 checks : claims validés, présents dans le transparency log, signés par notre clé)
```

### 3.5 Admission (Kyverno) — politiques appliquées

Quatre `ClusterPolicy` en `validationFailureAction: Enforce` (et non `Audit` : c'est le réglage
qui fait passer du « on observe » au « on **bloque** »). Toutes `Ready` :

```
$ kubectl get clusterpolicy
NAME                             ADMISSION   READY
allowed-registries               true        True
disallow-latest-tag              true        True
require-provenance-attestation   true        True
verify-image-signature           true        True
```

Installées en **server-side apply** (`kubectl apply --server-side --force-conflicts`) car les
CRD Kyverno dépassent la limite d'annotation de 262 144 octets du client-side apply.

## 4. Démonstration attaque / défense

**Image légitime déployée → ACCEPTÉE** (2 réplicas, image par digest, service en ligne) :

```
$ kubectl get pods -n app
scs-demo-app-676597786d-9sn8b   1/1   Running
scs-demo-app-676597786d-h68fm   1/1   Running
$ curl -s http://localhost:18080/health
{"status":"ok","version":"1.0.0"}
```

**Cinq attaques → toutes REFUSÉES** (messages Kyverno réels, abrégés) :

| # | Scénario | Résultat | Contrôle déclenché | Message Kyverno |
|---|---|---|---|---|
| — | Image signée + provenance | ✅ acceptée | — | pod `Running` |
| 1 | Image **non signée** | ❌ refusée | verify-image-signature | `no signatures found` |
| 2 | Image **altérée après signature** | ❌ refusée | verify-image-signature | `no signatures found` (nouveau digest) |
| 3 | **Registry non autorisé** (docker.io) | ❌ refusée | allowed-registries | `seules les images de ghcr.io/cedricgautier/ sont autorisées` |
| 4 | Tag **`:latest`** | ❌ refusée | signature/provenance | `image tag not found … MANIFEST_UNKNOWN` |
| 5 | **Signée mais SANS provenance** | ❌ refusée | require-provenance-attestation **seule** | `no matching attestations` |

Deux observations d'esprit critique :

- **Attaque 4 (`:latest`)** : le tag est bien bloqué, mais par la **couche signature** (l'image
  `:latest` n'existe pas / n'est pas signée) *avant* que `disallow-latest-tag` ne s'exprime.
  Les politiques se recouvrent : c'est de la **défense en profondeur**, `disallow-latest-tag`
  reste utile comme filet indépendant de la signature.
- **Attaque 5** : l'image **est** signée, donc `verify-image-signature` **passe** ; seule
  `require-provenance-attestation` refuse. C'est la **preuve d'isolation** que la politique de
  provenance agit indépendamment de la signature (bonus valorisé §4 du sujet).

## 5. Positionnement SLSA & limites

**Niveau réellement atteint : ~SLSA L1 en local, ~L2 via la CI** (lab 5, `.github/workflows/`).

- La **provenance existe** et est signée → satisfait la propriété de base de L1.
- En **local**, le build a lieu sur un poste de dev et la provenance est **auto-générée** : elle
  atteste peu de choses d'infalsifiable → on reste honnêtement à **L1**.
- En **CI** (GitHub Actions, keyless OIDC), le build est sur une **plateforme hébergée** et la
  signature porte l'**identité du workflow** (`…/supply-chain.yml@refs/heads/main`) → on
  approche **L2**.

**Ce qui reste contournable dans notre setup :**

1. **Le build lui-même** n'est pas isolé : un mainteneur avec les droits peut modifier le
   workflow ou le `Dockerfile` → il faudrait un build éphémère non contournable (L3).
2. **La provenance locale** est déclarative (prédicat écrit par nous), pas émise par un
   générateur isolé type `slsa-github-generator`.
3. **RBAC du cluster** non durci : Kyverno empêche une mauvaise image, pas un acteur disposant
   déjà de droits d'admin.
4. **Package GHCR public** : nécessaire pour que Kyverno lise image + artefacts sans secret ;
   en production on préférerait un `imagePullSecret`.

**Pistes L3 :** `slsa-github-generator` en job séparé, revue obligatoire, séparation stricte
build/signature.

## 6. Reproductibilité

Toute la démo se reconstruit de zéro. Prérequis : cosign **2.x** (`./cosign2`), syft, grype,
k3d, kubectl, jq, et `docker login ghcr.io`.

```bash
export GHCR_USER=<votre-user> COSIGN_PASSWORD=""
./scs.py all     --host-port 18080 --cosign ./cosign2   # build→…→cluster→deploy (pod Running)
# rendre le package GHCR public une fois (UI GitHub)
./scs.py attacks                  --cosign ./cosign2    # 5/5 refus
./scs.py scan-vuln                                      # Lab 1.4 : la gate casse
./scs.py verify                   --cosign ./cosign2    # preuves cosign
./scs.py clean                                          # supprime cluster + .local/
```

Pièges rencontrés et corrigés : voir [`../docs/04-depannage-local.md`](../docs/04-depannage-local.md)
(cosign 2.x vs 3.x, limite 2 Mio, UID numérique, `/tmp` inscriptible, port hôte, server-side apply).

## 7. Bilan

**Appris :** la sécurité de la chaîne d'appro n'est pas « un scan de plus » — c'est le
déplacement du contrôle **au moment de l'admission** (zero-trust : on vérifie, on ne fait pas
confiance). La distinction **scan** (détecte) vs **admission** (empêche) est centrale.

**Ce qu'on ferait différemment :** partir directement en **keyless/CI** pour ne pas gérer de clé
locale, et viser `slsa-github-generator` pour une provenance non déclarative.

**Répartition du travail** (traçable dans l'historique Git, un commit par membre) :

| Membre | Contribution |
|---|---|
| Cedric Gautier | durcissement image (UID non-root numérique) + lab CI/CD bout-en-bout |
| Barnabé Pilliaudin | orchestrateur Python `scs.py` + variabilisation des manifestes `${GHCR_USER}` |
| Magali Deslous-Paoli | documentation : lancement local, dépannage, rapport de vérification |

## Annexes

- Sorties brutes complètes : `docs/05-rapport-verification.md`, et sorties `cosign verify` /
  `verify-attestation` / `tree` (7 signatures présentes, l'image ayant été re-signée au fil des
  démos ; `verifiedCount` ≥ 1 suffit à la politique).
- Threat model : [`threat-model.md`](threat-model.md).
- Transparency log Rekor (par clé) : `logIndex` visibles dans la sortie `cosign verify`
  (ex. `2172059688`), interrogeables sur https://rekor.sigstore.dev.
