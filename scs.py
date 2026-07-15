#!/usr/bin/env python3
"""Point d'entrée de l'orchestrateur — délègue au package `supplychain`.

Toute la logique vit dans supplychain/ (un module par responsabilité).
Ce fichier ne fait que rendre `./scs.py <commande>` exécutable depuis n'importe quel dossier.

    ./scs.py all     --user <ghcr-user> --host-port 8080 --cosign ./cosign2
    ./scs.py attacks --user <ghcr-user>                   --cosign ./cosign2
    ./scs.py verify  --cosign ./cosign2
    ./scs.py clean
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from supplychain.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
