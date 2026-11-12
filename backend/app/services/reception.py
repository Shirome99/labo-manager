"""Non-conformités à la réception (colonnes nc_* de la migration 017) : libellés partagés."""

NON_CONFORMITES = [
    ("nc_temperature", "Température"),
    ("nc_contenant", "Contenant"),
    ("nc_quantite", "Quantité insuffisante"),
    ("nc_etiquetage", "Étiquetage"),
    ("nc_delai", "Délai d'acheminement"),
    ("nc_autre", "Autre"),
]


def _lire(e, attr):
    return e.get(attr) if isinstance(e, dict) else getattr(e, attr, None)


def liste_non_conformites(e) -> list[str]:
    """Libellés des non-conformités cochées (objet ORM ou dict)."""
    return [lib for attr, lib in NON_CONFORMITES if _lire(e, attr)]
