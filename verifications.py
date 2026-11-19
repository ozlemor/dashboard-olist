"""
Projet Olist — Vérifications : les KPI calculés en SQL doivent être les mêmes que dans 01_exploration.
Usage : python3 verifications.py
"""
import sqlite3
from contextlib import closing

import pandas as pd

with closing(sqlite3.connect("olist.db")) as con:

    # 1) Les KPI généraux (Q1)
    print("1) KPI généraux")
    print(pd.read_sql_query("""
        SELECT COUNT(*)                            AS commandes,
               ROUND(AVG(delai_livraison_j), 1)    AS delai_moyen_j,
               ROUND(AVG(delai_preparation_j), 1)  AS preparation_j,
               ROUND(AVG(delai_transport_j), 1)    AS transport_j,
               ROUND(AVG(delai_promis_j), 1)       AS promis_j,
               SUM(en_retard)                      AS commandes_en_retard,
               ROUND(AVG(en_retard) * 100, 1)      AS taux_retard_pct
        FROM livraisons
    """, con).to_string(index=False))

    # 2) Note moyenne : à l'heure / en retard (Q1)
    print("\n2) Note moyenne selon le retard")
    print(pd.read_sql_query("""
        SELECT CASE en_retard WHEN 1 THEN 'en retard' ELSE 'à l''heure' END AS livraison,
               COUNT(note)          AS avis,
               ROUND(AVG(note), 2)  AS note_moyenne
        FROM livraisons
        GROUP BY en_retard
    """, con).to_string(index=False))

    # 3) Délai par région : préparation et transport (Q5)
    print("\n3) Par région du client")
    print(pd.read_sql_query("""
        SELECT region_client,
               COUNT(*)                           AS commandes,
               ROUND(AVG(delai_preparation_j), 1) AS preparation_j,
               ROUND(AVG(delai_transport_j), 1)   AS transport_j,
               ROUND(AVG(en_retard) * 100, 1)     AS taux_retard_pct
        FROM livraisons
        GROUP BY region_client
        ORDER BY transport_j DESC
    """, con).to_string(index=False))