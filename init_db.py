"""
Projet Olist — Création de la base SQLite à partir des CSV bruts de data/.
Usage : python3 init_db.py      (recrée entièrement le fichier olist.db)
"""
import os
import sqlite3

import pandas as pd

FICHIER_DB = "olist.db"
DOSSIER = "data"

# ---------------------------------------------------------------------
# Table de référence : les 27 états, leur nom et leur région
# ---------------------------------------------------------------------
REGIONS = {"Sud-Est": ["ES", "MG", "RJ", "SP"],
           "Sud": ["PR", "RS", "SC"],
           "Centre-Ouest": ["DF", "GO", "MS", "MT"],
           "Nord-Est": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
           "Nord": ["AC", "AM", "AP", "PA", "RO", "RR", "TO"]}
NOMS_ETATS = {"AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
              "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
              "MG": "Minas Gerais", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará",
              "PB": "Paraíba", "PE": "Pernambuco", "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro",
              "RN": "Rio Grande do Norte", "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul",
              "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo", "TO": "Tocantins"}

# ---------------------------------------------------------------------
# 1. Schéma : 7 tables reliées par des clés
# ---------------------------------------------------------------------
SCHEMA = """
CREATE TABLE etats (
    etat        TEXT PRIMARY KEY,          -- 'SP', 'RJ'...
    nom         TEXT NOT NULL,
    region      TEXT NOT NULL
);

CREATE TABLE geolocalisation (
    code_postal INTEGER PRIMARY KEY,       -- 5 premiers chiffres du code postal
    latitude    REAL NOT NULL,
    longitude   REAL NOT NULL
);

CREATE TABLE clients (
    id_client   TEXT PRIMARY KEY,
    code_postal INTEGER,
    ville       TEXT,
    etat        TEXT REFERENCES etats(etat)
);

CREATE TABLE vendeurs (
    id_vendeur  TEXT PRIMARY KEY,
    code_postal INTEGER,
    ville       TEXT,
    etat        TEXT REFERENCES etats(etat)
);

CREATE TABLE commandes (
    id_commande              TEXT PRIMARY KEY,
    id_client                TEXT NOT NULL REFERENCES clients(id_client),
    statut                   TEXT NOT NULL,
    date_achat               TEXT NOT NULL,   -- format 'AAAA-MM-JJ HH:MM:SS'
    date_remise_transporteur TEXT,            -- le vendeur donne le colis au transporteur
    date_livraison           TEXT,            -- le client reçoit le colis
    date_promise             TEXT             -- date de livraison promise au client
);

CREATE TABLE articles (
    id_commande TEXT NOT NULL REFERENCES commandes(id_commande),
    num_article INTEGER NOT NULL,
    id_produit  TEXT NOT NULL,
    id_vendeur  TEXT NOT NULL REFERENCES vendeurs(id_vendeur),
    prix        REAL NOT NULL,                -- en reais (R$)
    fret        REAL NOT NULL,                -- frais de port (R$)
    PRIMARY KEY (id_commande, num_article)
);

CREATE TABLE avis (
    id_commande TEXT PRIMARY KEY REFERENCES commandes(id_commande),   -- un seul avis par commande
    note        INTEGER NOT NULL CHECK (note BETWEEN 1 AND 5),
    date_avis   TEXT
);

CREATE INDEX idx_commandes_client ON commandes(id_client);
CREATE INDEX idx_articles_vendeur ON articles(id_vendeur);

-- ---------------------------------------------------------------------
-- VUE : les commandes livrées et nettoyées, avec tous les KPI calculés en SQL
-- (mêmes règles que dans 01_exploration : livrées, janv. 2017 - août 2018, dates cohérentes)
-- julianday() transforme une date en nombre de jours : la différence donne une durée en jours.
-- ---------------------------------------------------------------------
CREATE VIEW livraisons AS
SELECT co.id_commande,
       co.date_achat,
       cl.etat                                                              AS etat_client,
       e.region                                                             AS region_client,
       julianday(co.date_livraison)           - julianday(co.date_achat)    AS delai_livraison_j,
       julianday(co.date_remise_transporteur) - julianday(co.date_achat)    AS delai_preparation_j,
       julianday(co.date_livraison)           - julianday(co.date_remise_transporteur) AS delai_transport_j,
       julianday(co.date_promise)             - julianday(co.date_achat)    AS delai_promis_j,
       julianday(date(co.date_livraison))     - julianday(date(co.date_promise))       AS retard_j,
       CASE WHEN date(co.date_livraison) > date(co.date_promise) THEN 1 ELSE 0 END    AS en_retard,
       av.note
FROM commandes co
JOIN clients cl     ON cl.id_client = co.id_client
JOIN etats e        ON e.etat = cl.etat
LEFT JOIN avis av   ON av.id_commande = co.id_commande
WHERE co.statut = 'delivered'
  AND co.date_livraison IS NOT NULL
  AND co.date_remise_transporteur IS NOT NULL
  AND co.date_achat >= '2017-01-01' AND co.date_achat < '2018-09-01'
  AND co.date_remise_transporteur >= co.date_achat
  AND co.date_livraison >= co.date_remise_transporteur;
"""


def lire(nom):
    return pd.read_csv(os.path.join(DOSSIER, nom))


def main():
    if os.path.exists(FICHIER_DB):
        os.remove(FICHIER_DB)                       # on repart toujours d'une base vide

    con = sqlite3.connect(FICHIER_DB)
    try:
        con.executescript(SCHEMA)

        # États
        lignes = [(e, NOMS_ETATS[e], r) for r, etats in REGIONS.items() for e in etats]
        con.executemany("INSERT INTO etats VALUES (?, ?, ?)", lignes)

        # Géolocalisation : une position par code postal, préparée une fois par preparer_geo.py
        geo = lire("geolocalisation_cp.csv")
        geo.to_sql("geolocalisation", con, if_exists="append", index=False)

        # Clients et vendeurs
        c = lire("olist_customers_dataset.csv")
        c = c[["customer_id", "customer_zip_code_prefix", "customer_city", "customer_state"]]
        c.columns = ["id_client", "code_postal", "ville", "etat"]
        c.to_sql("clients", con, if_exists="append", index=False)

        v = lire("olist_sellers_dataset.csv")
        v.columns = ["id_vendeur", "code_postal", "ville", "etat"]
        v.to_sql("vendeurs", con, if_exists="append", index=False)

        # Commandes (toutes, même non livrées : le filtre se fait en SQL)
        o = lire("olist_orders_dataset.csv")
        o = o[["order_id", "customer_id", "order_status", "order_purchase_timestamp",
               "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]]
        o.columns = ["id_commande", "id_client", "statut", "date_achat",
                     "date_remise_transporteur", "date_livraison", "date_promise"]
        o.to_sql("commandes", con, if_exists="append", index=False)

        # Articles
        a = lire("olist_order_items_dataset.csv")
        a = a[["order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value"]]
        a.columns = ["id_commande", "num_article", "id_produit", "id_vendeur", "prix", "fret"]
        a.to_sql("articles", con, if_exists="append", index=False)

        # Avis : un seul par commande (le plus récent), comme dans l'exploration
        r = lire("olist_order_reviews_dataset.csv")
        r = r.sort_values("review_creation_date").drop_duplicates("order_id", keep="last")
        r = r[["order_id", "review_score", "review_creation_date"]]
        r.columns = ["id_commande", "note", "date_avis"]
        r.to_sql("avis", con, if_exists="append", index=False)

        con.commit()
        for table in ["etats", "geolocalisation", "clients", "vendeurs", "commandes", "articles", "avis"]:
            n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"Table {table:16s}: {n:>7} lignes")
        n = con.execute("SELECT COUNT(*) FROM livraisons").fetchone()[0]
        print(f"Vue   livraisons      : {n:>7} commandes livrées et nettoyées")
    finally:
        con.close()
    print(f"Base créée : {FICHIER_DB}")


if __name__ == "__main__":
    main()