-- ============================================================
-- LIMS LRARVY — Reporting de la facturation (tâche 40, bloc P)
-- Migration ADDITIVE : requêtes partagées et blocs du bilan mensuel ajoutés, rien n'est modifié.
--
-- Le jeu « facturation » du catalogue (app/services/requetes.py) est le journal des mouvements des
-- bulletins émis (lignes facturées, avoirs, exonérations, encaissements). Trois requêtes partagées
-- forment la section « Facturation » du bilan mensuel : facturé / avoirs / exonérations / encaissé /
-- reste par section, encaissements par mode de paiement, impayés à la date du bilan.
-- Le bloc existant « Facturation du mois » (migration 024) reste en place ; l'admin peut le désactiver
-- dans Bilan mensuel > Composition.
-- ============================================================

INSERT INTO requetes_enregistrees (nom, description, definition, auteur, visibilite)
SELECT v.nom, v.description, v.definition::jsonb, 'système', 'partagée'
FROM (VALUES
    ('Facturation du mois par section',
     'Bulletins émis le mois précédent : facturé, avoirs, exonérations, encaissé et reste à recouvrer, par section.',
     '{"jeu": "facturation", "filtres": {"periode": "mois_precedent", "date_ref": "emission_bulletin"}, "regroupements": ["section"], "mesures": ["nb_bulletins", "montant", "montant_avoirs", "montant_exonere", "montant_paye", "reste_a_payer"]}'),
    ('Encaissements par mode de paiement',
     'Encaissements du mois précédent (date du paiement), par mode de paiement.',
     '{"jeu": "facturation", "filtres": {"periode": "mois_precedent", "date_ref": "mouvement", "type_mouvement": ["Encaissement"]}, "regroupements": ["mode_paiement"], "mesures": ["nb_bulletins", "montant_paye"]}'),
    ('Impayés par section',
     'Reste à recouvrer de tous les bulletins émis, par section (situation à la date d''exécution).',
     '{"jeu": "facturation", "filtres": {}, "regroupements": ["section"], "mesures": ["nb_bulletins", "montant", "montant_avoirs", "montant_exonere", "montant_paye", "reste_a_payer"]}')
) AS v (nom, description, definition)
WHERE NOT EXISTS (SELECT 1 FROM requetes_enregistrees r WHERE r.auteur = 'système' AND r.nom = v.nom);

INSERT INTO bilan_modele (ordre, type_bloc, titre, requete_id)
SELECT m.ordre, 'requete', m.titre, r.id
FROM (VALUES
    (11, 'Facturation : bulletins du mois par section', 'Facturation du mois par section'),
    (12, 'Facturation : encaissements du mois par mode de paiement', 'Encaissements par mode de paiement'),
    (13, 'Facturation : impayés (à la date du bilan)', 'Impayés par section')
) AS m (ordre, titre, nom_requete)
JOIN requetes_enregistrees r ON r.auteur = 'système' AND r.nom = m.nom_requete
WHERE EXISTS (SELECT 1 FROM bilan_modele)
  AND NOT EXISTS (SELECT 1 FROM bilan_modele b WHERE b.titre = m.titre);
