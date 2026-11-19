Livraisons Olist : où, quand et pourquoi les commandes sont en retard ?

Dashboard en ligne : https://dashboard-olist.onrender.com (lien à mettre à jour après le déploiement) (plan gratuit Render : le premier chargement peut prendre 2 à 3 minutes)

Projet du module Visualisation interactive (MSc2 DATA). Données publiques Olist (marketplace brésilienne, Kaggle) : 99 441 commandes, 2016–2018.

Question : où, quand et pourquoi les livraisons sont-elles en retard, et combien cela coûte-t-il en satisfaction client ?

Résultats : 6,8 % des commandes sont en retard, et la note client passe de 4,3 à 2,3. Le problème vient du transport vers le Nord-Est et de dates promises trop courtes, pas des vendeurs. Trois actions permettent d'éviter 1 183 retards (−18 %).

Organisation du dashboard : une histoire en 3 chapitres
Chapitre	Question	Graphiques
I. Le problème	1. C'est grave ?	chiffres clés, barres (note selon le retard)
	2. Quand ?	courbe du retard par semaine
	3. Où ?	carte Folium, heatmap vendeur → client
II. La cause	4. Pourquoi ?	barres empilées (préparation / transport), nuage de points (marge)
III. La solution	5. Que faire ?	tableau des priorités, waterfall de simulation (3 curseurs)

Les filtres (région, période) restent en haut de l'écran et changent toute la page.

Fichiers
Fichier	Rôle
app.py	Dashboard Dash : chiffres clés, 7 graphiques Plotly, carte Folium, plan d'action. Expose server = app.server
db.py	Requêtes SQL paramétrées (filtres région et période)
init_db.py	Crée la base SQLite (7 tables + 1 vue) à partir des CSV, à chaque démarrage
preparer_geo.py	Script lancé une fois : réduit la géolocalisation (1 million de lignes -> 19 010)
verifications.py	Vérifie que les KPI SQL sont les mêmes que dans le notebook
data/	CSV bruts Olist
Lancer en local
bash
pip install -r requirements.txt
python preparer_geo.py      # une seule fois
python app.py
Déploiement Render
Build : pip install -r requirements.txt
Start : gunicorn app:server --preload --timeout 120
Le fichier .db n'est pas sur GitHub : il est recréé au démarrage à partir des CSV.

Source des données : Brazilian E-Commerce Public Dataset by Olist (Kaggle)