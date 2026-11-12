"""
Contrôles qualité internes (tâche 18) : analyse d'une série (carte de contrôle).

Quantitatif : moyenne et écart-type de référence (fixés sur la série, sinon calculés
sur ses mesures, échantillon n-1), limites ±2σ / ±3σ, et deux règles d'alerte :
  - « hors ±3σ »      : |valeur - moyenne| > 3σ ;
  - « 7 points »      : 7 points consécutifs (ou plus) strictement du même côté de la moyenne ;
    les points concernés, à partir du 7e, portent l'alerte.
Qualitatif : alerte si le résultat diffère du résultat attendu.
L'alerte est « active » quand la dernière mesure en porte une.
"""
from statistics import mean, stdev

RUN = 7


def analyser(serie: dict, mesures: list[dict]) -> dict:
    if serie["nature"] == "qualitatif":
        attendu = (serie.get("resultat_attendu") or "").strip().lower()
        points = []
        for m in mesures:
            ok = not attendu or (m.get("resultat") or "").strip().lower() == attendu
            points.append({**m, "zone": "ok" if ok else "3s",
                           "regles": [] if ok else [f"résultat « {m.get('resultat')} » ≠ attendu « {serie.get('resultat_attendu')} »"]})
        return _resume(points, {})

    valeurs = [float(m["valeur"]) for m in mesures if m.get("valeur") is not None]
    moyenne = float(serie["moyenne_ref"]) if serie.get("moyenne_ref") is not None else (mean(valeurs) if valeurs else None)
    if serie.get("ecart_type_ref") is not None:
        sigma = float(serie["ecart_type_ref"])
    else:
        sigma = stdev(valeurs) if len(valeurs) >= 2 else None
    stats = {"moyenne": moyenne, "sigma": sigma, "reference": serie.get("moyenne_ref") is not None,
             "n": len(valeurs)}
    if moyenne is not None and sigma:
        stats.update({"lim_2s": [moyenne - 2 * sigma, moyenne + 2 * sigma],
                      "lim_3s": [moyenne - 3 * sigma, moyenne + 3 * sigma]})

    points, cote_prec, longueur = [], 0, 0
    for m in mesures:
        p = {**m, "zone": "ok", "regles": []}
        v = m.get("valeur")
        if v is not None and moyenne is not None:
            v = float(v)
            if sigma:
                ecart = abs(v - moyenne)
                p["zone"] = "3s" if ecart > 3 * sigma else ("2s" if ecart > 2 * sigma else "ok")
                if ecart > 3 * sigma:
                    p["regles"].append("valeur hors ±3σ")
            cote = (v > moyenne) - (v < moyenne)
            longueur = longueur + 1 if cote != 0 and cote == cote_prec else (1 if cote != 0 else 0)
            cote_prec = cote
            if longueur >= RUN:
                p["regles"].append(f"{longueur} points consécutifs {'au-dessus' if cote > 0 else 'au-dessous'} de la moyenne")
        points.append(p)
    return _resume(points, stats)


def _resume(points: list[dict], stats: dict) -> dict:
    alertes = [{"mesure_id": p["id"], "date_mesure": p["date_mesure"], "valeur": p.get("valeur"),
                "resultat": p.get("resultat"), "regles": p["regles"]} for p in points if p["regles"]]
    return {"stats": stats, "points": points, "alertes": alertes,
            "alerte_active": bool(points and points[-1]["regles"])}
