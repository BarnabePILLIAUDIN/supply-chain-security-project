"""Orchestration locale de la chaîne d'approvisionnement logicielle (labs 0→4).

Modules (une responsabilité chacun) :
  config     paramètres du run (immuables, injectés partout)
  shell      exécution de commandes + helpers git/FS (feuille)
  image      Lab 0 — build / push / export de l'image
  sbom       Lab 1 — SBOM + scan (gate)
  signing    Lab 2 — signature cosign + attestations
  manifests  rendu des templates -> .local/
  cluster    Lab 3 — k3d / Kyverno / politiques / déploiement
  attacks    Lab 4 — scénarios attaque/défense
  verify     preuves cosign (signature + attestation)
  pipeline   orchestration (chaîne complète + nettoyage)
  cli        contrôleur (argparse -> fonction métier)
"""
