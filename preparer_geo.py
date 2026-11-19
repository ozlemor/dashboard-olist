"""
Projet Olist — Script à lancer UNE SEULE FOIS sur votre ordinateur (comme convertir_csv.py au TP5).
Le fichier brut de géolocalisation est très gros (1 million de lignes, 61 Mo) et contient des doublons.
On garde UNE position moyenne par code postal : environ 19 000 lignes (moins de 1 Mo).
Pourquoi : sur Render (plan gratuit, 0,1 CPU), la base est recréée à chaque démarrage.
Lire 19 000 lignes au lieu d'un million rend le démarrage beaucoup plus rapide.
Usage : python3 preparer_geo.py
"""
import pandas as pd

geo = pd.read_csv("data/olist_geolocation_dataset.csv")
print("Fichier brut :", len(geo), "lignes")

# Coordonnées au Brésil seulement, puis une position moyenne par code postal
geo = geo[geo["geolocation_lat"].between(-34, 6) & geo["geolocation_lng"].between(-74, -34)]
geo = (geo.groupby("geolocation_zip_code_prefix")[["geolocation_lat", "geolocation_lng"]].mean()
          .reset_index())
geo.columns = ["code_postal", "latitude", "longitude"]
geo.to_csv("data/geolocalisation_cp.csv", index=False)
print("Fichier créé : data/geolocalisation_cp.csv,", len(geo), "lignes")