"""
Projet Olist — Module d'accès aux données (comme db.py du TP4).
Toutes les lectures de la base passent par ici. Chaque fonction ouvre une connexion,
exécute sa requête, puis ferme la connexion.

Deux étapes :
1. calculer_faits() : à partir des tables brutes et de la vue « livraisons », on (re)calcule
   la table « faits_livraisons » (une ligne par commande, avec tous les KPI). C'est fait au démarrage
   et à chaque clic sur Refresh : toute modification des tables brutes est donc prise en compte.
   Le calcul est fait dans une transaction (BEGIN ... COMMIT) : pendant ce temps, le dashboard
   continue de lire l'ancienne table, jamais une table à moitié construite.
2. les autres fonctions interrogent cette table avec les filtres du dashboard (régions, période).
"""
import sqlite3
from contextlib import closing

import pandas as pd

from init_db import FICHIER_DB


def executer(requete, parametres=()):
    """Ouvre une connexion, exécute la requête, renvoie un DataFrame, puis ferme la connexion."""
    with closing(sqlite3.connect(FICHIER_DB)) as con:
        return pd.read_sql_query(requete, con, params=parametres)


# ---------------------------------------------------------------------
# 1. Table de faits : une ligne par commande livrée, avec tous les KPI
# ---------------------------------------------------------------------
CALCUL_FAITS = """
BEGIN;
DROP TABLE IF EXISTS faits_livraisons;

CREATE TABLE faits_livraisons AS
SELECT l.*,
       substr(l.date_achat, 1, 10)                AS jour_achat,
       v.etat                                     AS etat_vendeur,
       gc.latitude  AS lat_client,  gc.longitude  AS lon_client,
       gv.latitude  AS lat_vendeur, gv.longitude  AS lon_vendeur,
       a.id_vendeur,
       m.montant
FROM livraisons l
JOIN commandes co            ON co.id_commande = l.id_commande
JOIN clients cl              ON cl.id_client = co.id_client
LEFT JOIN geolocalisation gc ON gc.code_postal = cl.code_postal
JOIN articles a              ON a.id_commande = l.id_commande AND a.num_article = 1   -- vendeur du 1er article
JOIN vendeurs v              ON v.id_vendeur = a.id_vendeur
LEFT JOIN geolocalisation gv ON gv.code_postal = v.code_postal
JOIN (SELECT id_commande, SUM(prix + fret) AS montant
      FROM articles GROUP BY id_commande) m ON m.id_commande = l.id_commande;

CREATE INDEX idx_faits_region ON faits_livraisons(region_client);
CREATE INDEX idx_faits_jour   ON faits_livraisons(jour_achat);
COMMIT;
"""


def calculer_faits():
    """(Re)calcule la table faits_livraisons à partir des tables brutes. Renvoie le nombre de commandes."""
    with closing(sqlite3.connect(FICHIER_DB)) as con:
        con.executescript(CALCUL_FAITS)
        return con.execute("SELECT COUNT(*) FROM faits_livraisons").fetchone()[0]


# ---------------------------------------------------------------------
# 2. Filtres du dashboard -> clause WHERE (avec des paramètres « ? », jamais de texte collé)
# ---------------------------------------------------------------------
def filtre(regions, debut, fin):
    """regions : liste de régions ; debut, fin : dates 'AAAA-MM-JJ' (fin incluse)."""
    marques = ", ".join("?" * len(regions))
    where = f"WHERE region_client IN ({marques}) AND jour_achat >= ? AND jour_achat <= ?"
    return where, list(regions) + [debut, fin]


def kpis(regions, debut, fin):
    """Les chiffres clés (Q1)."""
    where, p = filtre(regions, debut, fin)
    return executer(f"""
        SELECT COUNT(*)                                          AS commandes,
               AVG(delai_livraison_j)                            AS delai_moyen,
               AVG(delai_promis_j)                               AS delai_promis,
               SUM(en_retard)                                    AS commandes_en_retard,
               AVG(en_retard) * 100                              AS taux_retard,
               AVG(CASE WHEN en_retard = 0 THEN note END)        AS note_heure,
               AVG(CASE WHEN en_retard = 1 THEN note END)        AS note_retard,
               SUM(CASE WHEN en_retard = 1 THEN montant END)     AS ca_retard
        FROM faits_livraisons {where}
    """, p).iloc[0]


def notes_par_retard(regions, debut, fin):
    """Part des notes 1-2 selon la durée du retard (Q2)."""
    where, p = filtre(regions, debut, fin)
    return executer(f"""
        SELECT CASE WHEN retard_j <= 0  THEN '1. À l''heure'
                    WHEN retard_j <= 3  THEN '2. 1 à 3 j'
                    WHEN retard_j <= 7  THEN '3. 4 à 7 j'
                    WHEN retard_j <= 14 THEN '4. 8 à 14 j'
                    ELSE                     '5. Plus de 14 j' END            AS classe,
               COUNT(*)                                                       AS commandes,
               AVG(note)                                                      AS note_moyenne,
               100.0 * SUM(CASE WHEN note <= 2 THEN 1 ELSE 0 END) / COUNT(note) AS part_notes_1_2
        FROM faits_livraisons {where}
        GROUP BY classe ORDER BY classe
    """, p)


def serie_semaines(regions, debut, fin):
    """Commandes et taux de retard par semaine d'achat (Q3)."""
    where, p = filtre(regions, debut, fin)
    return executer(f"""
        SELECT date(jour_achat, 'weekday 1', '-7 days')  AS semaine,     -- le lundi de la semaine
               COUNT(*)                                  AS commandes,
               AVG(en_retard) * 100                      AS taux_retard
        FROM faits_livraisons {where}
        GROUP BY semaine ORDER BY semaine
    """, p)


def delais_par_region(regions, debut, fin):
    """Préparation et transport par région du client (Q5)."""
    where, p = filtre(regions, debut, fin)
    return executer(f"""
        SELECT region_client                 AS region,
               AVG(delai_preparation_j)      AS preparation,
               AVG(delai_transport_j)        AS transport,
               AVG(en_retard) * 100          AS taux_retard,
               COUNT(*)                      AS commandes
        FROM faits_livraisons {where}
        GROUP BY region_client
    """, p)


def par_etat(regions, debut, fin):
    """Une ligne par état du client : position, volume, retard, note, CA, marge (carte, Q6, Q7)."""
    where, p = filtre(regions, debut, fin)
    return executer(f"""
        SELECT f.etat_client                                 AS etat,
               e.nom, e.region,
               AVG(f.lat_client)                             AS lat,
               AVG(f.lon_client)                             AS lon,
               COUNT(*)                                      AS commandes,
               SUM(f.en_retard)                              AS en_retard,
               AVG(f.en_retard) * 100                        AS taux_retard,
               AVG(f.delai_livraison_j)                      AS delai,
               AVG(f.delai_promis_j) - AVG(f.delai_livraison_j) AS marge,
               AVG(f.note)                                   AS note,
               SUM(f.montant)                                AS ca,
               SUM(CASE WHEN f.en_retard = 1 THEN f.montant ELSE 0 END) AS ca_retard
        FROM faits_livraisons f
        JOIN etats e ON e.etat = f.etat_client
        {where.replace('region_client', 'f.region_client').replace('jour_achat', 'f.jour_achat')}
        GROUP BY f.etat_client, e.nom, e.region
    """, p)


def routes(regions, debut, fin):
    """Taux de retard par état du vendeur x état du client (Q4)."""
    where, p = filtre(regions, debut, fin)
    return executer(f"""
        SELECT etat_vendeur, etat_client,
               COUNT(*)              AS commandes,
               AVG(en_retard) * 100  AS taux_retard
        FROM faits_livraisons {where}
        GROUP BY etat_vendeur, etat_client
    """, p)


def vendeurs(regions, debut, fin):
    """Les vendeurs regroupés par zone (~10 km) pour la carte : nombre de vendeurs et de commandes par zone."""
    where, p = filtre(regions, debut, fin)
    return executer(f"""
        SELECT ROUND(lat_vendeur, 1)          AS lat,
               ROUND(lon_vendeur, 1)          AS lon,
               MIN(etat_vendeur)              AS etat,
               COUNT(DISTINCT id_vendeur)     AS vendeurs,
               COUNT(*)                       AS commandes
        FROM faits_livraisons {where} AND lat_vendeur IS NOT NULL
        GROUP BY ROUND(lat_vendeur, 1), ROUND(lon_vendeur, 1)
    """, p)


def simulation(regions, debut, fin, marge_nord_est, gain_rio, marge_pics):
    """Q8 – Combien de retards évite-t-on avec les 3 actions ?
    Une commande en retard est « sauvée » si son retard (en jours) est plus petit que le gain de l'action.
    Chaque commande n'est comptée qu'une seule fois (action 1, sinon 2, sinon 3)."""
    where, p = filtre(regions, debut, fin)
    a1 = "(region_client = 'Nord-Est' AND retard_j <= ?)"
    a2 = "(etat_client = 'RJ' AND retard_j <= ?)"
    pic = ("((date_achat >= '2017-11-20' AND date_achat < '2017-12-04') "
           " OR (date_achat >= '2018-02-05' AND date_achat < '2018-03-26'))")
    a3 = f"({pic} AND retard_j <= ?)"
    requete = f"""
        SELECT COUNT(*)                                                                AS commandes,
               SUM(en_retard)                                                          AS avant,
               SUM(CASE WHEN en_retard = 1 AND {a1} THEN 1 ELSE 0 END)                 AS action1,
               SUM(CASE WHEN en_retard = 1 AND NOT {a1} AND {a2} THEN 1 ELSE 0 END)    AS action2,
               SUM(CASE WHEN en_retard = 1 AND NOT {a1} AND NOT {a2} AND {a3}
                        THEN 1 ELSE 0 END)                                             AS action3
        FROM faits_livraisons {where}
    """
    # les « ? » sont remplis dans l'ordre où ils apparaissent dans la requête
    parametres = [marge_nord_est,
                  marge_nord_est, gain_rio,
                  marge_nord_est, gain_rio, marge_pics] + p
    return executer(requete, parametres).iloc[0]