"""
Remplit une base de TEST avec un volume réaliste (tâche 30) : par défaut 22 000 échantillons
répartis sur 5 ans (jusqu'à aujourd'hui), avec fiches de traitement, résultats d'analyses,
décisions de réception, paiements et dates de remise des rapports.

Les valeurs (natures, catégories, types / sous-types, fabricants, organismes) sont tirées
des référentiels de la base. Les échantillons sont ajoutés à ceux qui existent (numéros
à la suite de chaque section et année). Les triggers d'audit restent actifs : le journal
`audit_donnees` grossit comme en production.

Usage (depuis backend/) :
    python scripts/preparer_base_test.py               # base vierge (facultatif)
    python scripts/remplir_volume.py [--nombre 22000] [--annees 5] [--base labo_test] [--graine 2026]
"""
import argparse
import asyncio
import random
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import migrer  # noqa: E402
from scripts.preparer_base_test import verifier_nom  # noqa: E402

ANALYSES = {
    "SMA": ["Escherichia coli", "Staphylocoque à coagulase positive", "Salmonella", "FMAT",
            "Listeria monocytogenes", "Levures et moisissures", "Coliformes totaux"],
    "SCHA": ["Histamine", "ABVT", "Plomb", "Cadmium", "Mercure", "Aflatoxine B1", "Humidité"],
    "SSA": ["Brucellose", "Tuberculose", "Rage", "Influenza aviaire", "Newcastle", "Salmonellose aviaire"],
}
ESPECES = ["Bovine", "Ovine", "Caprine", "Volaille", "Équine", "Canine", "Abeilles"]
PAIEMENTS = ["Non concerné"] * 5 + ["Payé"] * 3 + ["À payer", "Partiellement payé", "Exonéré"]
ANALYSTES = {"SMA": "sma1", "SCHA": "scha1", "SSA": "ssa1"}


def rp_sma(rng):
    return rng.choice(["<10", "<10", "<10", "Abs", "15", "40", "1,2x10^2", "<40", "3x10^3"])


async def remplir(base: str, nombre: int, annees: int, graine: int) -> None:
    verifier_nom(base)
    rng = random.Random(graine)
    conn = await asyncpg.connect(migrer.url(base))
    t0 = time.perf_counter()
    try:
        natures = [r[0] for r in await conn.fetch("SELECT libelle FROM ref_natures")]
        categories = [r[0] for r in await conn.fetch("SELECT libelle FROM ref_categories")]
        fabricants = [r[0] for r in await conn.fetch("SELECT libelle FROM ref_fabricants")]
        organismes = [r[0] for r in await conn.fetch("SELECT libelle FROM ref_organismes")]
        soustypes = [(r[0], r[1]) for r in await conn.fetch("SELECT type_id, id FROM ref_soustypes_echantillon WHERE type_id IS NOT NULL")]
        types = [r[0] for r in await conn.fetch("SELECT id FROM ref_types_echantillon")]
        # Suite des numéros par section et année
        compteurs = defaultdict(int)
        for num, in await conn.fetch("""SELECT "N° Echantillon" FROM echantillons WHERE "N° Echantillon" ~ '^\\d{4}-(SMA|SCHA|SSA)-\\d+$'"""):
            a, s, n = num.split("-")
            compteurs[(int(a), s)] = max(compteurs[(int(a), s)], int(n))

        aujourd_hui = date.today()
        debut = aujourd_hui - timedelta(days=365 * annees)
        jours = (aujourd_hui - debut).days
        # Activité croissante dans le temps (poids linéaire), heures de bureau
        dates = sorted(datetime.combine(debut + timedelta(days=int(jours * (rng.random() ** 0.8))), datetime.min.time())
                       + timedelta(hours=rng.randint(8, 15), minutes=rng.randint(0, 59)) for _ in range(nombre))

        ech, fiches, resultats = [], defaultdict(list), []
        for d in dates:
            sec = rng.choices(["SMA", "SCHA", "SSA"], weights=[5, 3, 2])[0]
            compteurs[(d.year, sec)] += 1
            num = f"{d.year}-{sec}-{compteurs[(d.year, sec)]:04d}"
            age = (aujourd_hui - d.date()).days
            decision = rng.choices(["Accepté", "Accepté sous réserve", "Refusé"], weights=[95, 3, 2])[0]
            if decision == "Refusé":
                statut = "Reçu"
            elif age > 60:
                statut = "Rapport émis" if rng.random() < 0.985 else rng.choice(["En cours", "À valider", "Validé"])
            else:
                statut = rng.choices(["Reçu", "En cours", "À valider", "Validé", "Rapport émis"],
                                     weights=[2, 3, 2, 1, max(1, age // 4)])[0]
            type_id, stype_id = rng.choice(soustypes) if soustypes and rng.random() < 0.9 else (rng.choice(types), None)
            nb_prl = rng.choice([1, 1, 2, 3, 5])
            emis = statut == "Rapport émis"
            remise = d + timedelta(days=rng.randint(4, 30)) if emis else None
            paiement = rng.choice(PAIEMENTS)
            total = str(rng.choice([80, 120, 150, 200, 300])) if paiement != "Non concerné" else None
            ech.append((
                num, d, rng.choice(natures),
                rng.choice(categories) if rng.random() < 0.8 else None,
                type_id, stype_id,
                rng.choice(ESPECES) if sec == "SSA" else None,
                nb_prl if sec == "SMA" else None, nb_prl if sec == "SCHA" else None, nb_prl if sec == "SSA" else None,
                f"L{rng.randint(1000, 99999)}", rng.choice(fabricants) if rng.random() < 0.9 else None,
                rng.choice(organismes) if rng.random() < 0.95 else None,
                "Yes" if sec == "SMA" else "No", "Yes" if sec == "SCHA" else "No", "Yes" if sec == "SSA" else "No",
                remise, paiement, total, statut, decision,
                ("Contenant non conforme" if decision != "Accepté" else None),
            ))
            if statut == "Reçu":
                continue
            valide = statut in ("Validé", "Rapport émis")
            analyse_le = (d + timedelta(days=rng.randint(0, 3))).date()
            nc = rng.random() < 0.08
            fiches[sec].append((num, nb_prl, analyse_le, ANALYSTES[sec], "resp1" if valide else None,
                                datetime.combine(analyse_le, datetime.min.time()) + timedelta(days=2) if valide else None,
                                ("Non conforme" if nc else "Conforme") if sec != "SSA" else ("Positif" if nc else "Négatif")))
            for a in rng.sample(ANALYSES[sec], rng.choice([1, 1, 2, 3])):
                if sec == "SMA":
                    rps = [rp_sma(rng) for _ in range(5)]
                    resultats.append((num, sec, a, analyse_le, *rps, None, None, None, None, None, None, ANALYSTES[sec]))
                elif sec == "SCHA":
                    v = f"{rng.uniform(0.1, 60):.1f}"
                    resultats.append((num, sec, a, analyse_le, v, None, None, None, None, v,
                                      "Non conforme" if nc else "Conforme", None, None, None, None, ANALYSTES[sec]))
                else:
                    pos = rng.randint(1, 3) if nc else 0
                    resultats.append((num, sec, a, analyse_le, "Positif" if pos else "Négatif", None, None, None, None,
                                      None, None, "Positif" if pos else "Négatif", pos, nb_prl, 0, ANALYSTES[sec]))

        colonnes_ech = [
            "N° Echantillon", "Date reception", "Nature de l'échantillon", "Catégorie de l'échantillon",
            "Type d'échantillon", "S/type d'échantillon", "Espèce animale",
            "Nbre Prlvmts SMA", "Nbre Prlvmts SCHA", "Nbre Prlvmts SSA", "N° de lot", "Fabricant ou Propriétaire",
            "Organisme préleveur", "SMA", "SCHA", "SSA", "Date 1 Remise Rapport", "Payement", "TOTAL",
            "statut", "decision_reception", "motif_decision"]
        # Libellés de référentiel plus longs que la colonne (ex. catégorie en varchar(50)) : tronqués
        longueurs = {r[0]: r[1] for r in await conn.fetch(
            "SELECT column_name, character_maximum_length FROM information_schema.columns "
            "WHERE table_name = 'echantillons' AND character_maximum_length IS NOT NULL")}
        maxi = [longueurs.get(col) for col in colonnes_ech]
        ech = [tuple(v[:m] if isinstance(v, str) and m else v for v, m in zip(ligne, maxi)) for ligne in ech]
        await conn.copy_records_to_table("echantillons", records=ech, columns=colonnes_ech)
        colonnes = ["num_echantillon", "nbre_prelevements", "date_mise_en_analyse", "saisi_par", "valide_par",
                    "date_validation"]
        for sec, lignes in fiches.items():
            table = f"traitement_{sec.lower()}"
            col_conf = "positivite" if sec == "SSA" else "conformite"
            await conn.copy_records_to_table(table, records=lignes, columns=colonnes + [col_conf])
        await conn.copy_records_to_table("resultats_analyses", records=resultats, columns=[
            "num_echantillon", "section", "analyse_effectuee", "date_analyse", "rp1", "rp2", "rp3", "rp4", "rp5",
            "moyenne", "conclusion", "resultat_analyse", "nbre_positifs", "nbre_negatif", "nbre_douteux", "saisi_par"])
        await conn.execute("ANALYZE")
        n_fiches = sum(len(v) for v in fiches.values())
        print(f"Base {base} : {len(ech)} échantillons ({dates[0]:%d/%m/%Y} → {dates[-1]:%d/%m/%Y}), "
              f"{n_fiches} fiches, {len(resultats)} résultats ajoutés en {time.perf_counter() - t0:.1f} s.")
    finally:
        await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Volume réaliste dans une base de test.")
    ap.add_argument("--base", default="labo_test")
    ap.add_argument("--nombre", type=int, default=22000)
    ap.add_argument("--annees", type=int, default=5)
    ap.add_argument("--graine", type=int, default=2026)
    a = ap.parse_args()
    asyncio.run(remplir(a.base, a.nombre, a.annees, a.graine))
