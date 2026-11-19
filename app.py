"""
Projet Olist — Dashboard « Livraisons et satisfaction client ».
Lancement : python3 app.py   puis ouvrir http://127.0.0.1:8050
Sur Render : gunicorn app:server --preload --timeout 120
Au démarrage : la base SQLite est recréée à partir des CSV (init_db.py),
puis la table des KPI est calculée (db.calculer_faits()).
Le bouton « Refresh » recalcule les KPI à partir de la base et remet tous les filtres.
"""
from datetime import datetime
from functools import lru_cache

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import folium
from folium.plugins import MarkerCluster
from dash import Dash, html, dcc, Input, Output, ctx, no_update

import db
import init_db

# =====================================================================
# 1. DÉMARRAGE : base recréée à partir des CSV, puis calcul des KPI
# =====================================================================
init_db.main()
INFO = {"texte": f"KPI calculés depuis la base SQLite à {datetime.now():%H:%M:%S} · "
                 f"{db.calculer_faits():,} commandes livrées".replace(",", " ")}

REGIONS = list(init_db.REGIONS.keys())        # Sud-Est, Sud, Centre-Ouest, Nord-Est, Nord
MOIS = pd.date_range("2017-01-01", "2018-08-01", freq="MS")         # les 20 mois étudiés
NOMS_MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

# Couleurs (comme dans le notebook) : une seule couleur d'accent, le rouge = retard
ROUGE, BLEU, GRIS, GRIS_FONCE = "#B4483F", "#1B6A8F", "#9CA3AF", "#4B5563"
COULEURS_TRANCHE = {"Moins de 5 %": GRIS, "5 à 10 %": "#E8A598", "Plus de 10 %": ROUGE}


def fr(x, dec=0):
    """Format français : espace pour les milliers, virgule pour les décimales."""
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")


def periode(valeur_slider):
    """Indices du curseur [i, j] -> dates 'AAAA-MM-JJ' (du 1er jour du mois i au dernier jour du mois j)."""
    i, j = valeur_slider
    debut = MOIS[i]
    fin = MOIS[j] + pd.offsets.MonthEnd(0)
    return debut.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d")


def mise_en_forme(fig, titre, sous_titre=None, hauteur=400):
    """Style commun (comme au TP1) : titre-message + sous-titre, fond blanc."""
    texte = f"<b>{titre}</b>"
    if sous_titre:
        texte += f"<br><span style='font-size:12px;color:#6B7280'>{sous_titre}</span>"
    fig.update_layout(template="simple_white", height=hauteur, separators=", ",
                      title=dict(text=texte, x=0.02, xanchor="left", font=dict(size=15)),
                      font=dict(family="Arial", size=12, color="#1F2937"),
                      margin=dict(t=85, l=55, r=20, b=45), showlegend=False)
    return fig


def figure_vide(message):
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=14, color="#6B7280"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return mise_en_forme(fig, "Aucune donnée", hauteur=300)


# =====================================================================
# 2. LES CHIFFRES CLÉS (Q1) : 4 cartes HTML
# =====================================================================
def carte_kpi(etiquette, valeur, detail, couleur):
    return html.Div(className="kpi", style={"borderTop": f"4px solid {couleur}"}, children=[
        html.Div(etiquette, className="kpi-etiquette"),
        html.Div(valeur, className="kpi-valeur", style={"color": couleur}),
        html.Div(detail, className="kpi-detail"),
    ])


def cartes_kpi(k):
    return [
        carte_kpi("COMMANDES LIVRÉES", fr(k["commandes"]), "sur la période choisie", GRIS_FONCE),
        carte_kpi("DÉLAI DE LIVRAISON", f"{fr(k['delai_moyen'], 1)} j", f"promis : {fr(k['delai_promis'], 1)} j", BLEU),
        carte_kpi("COMMANDES EN RETARD", f"{fr(k['taux_retard'], 1)} %",
                  f"{fr(k['commandes_en_retard'])} commandes · {fr(k['ca_retard'] / 1e6, 2)} M R$", ROUGE),
        carte_kpi("NOTE SI RETARD", f"{fr(k['note_retard'], 1)} / 5", f"contre {fr(k['note_heure'], 1)} à l'heure", ROUGE),
    ]


# =====================================================================
# 3. LES GRAPHIQUES (Q2 à Q7), recalculés avec les filtres
# =====================================================================
def figure_notes(t):
    """Q2 – bar : part des notes 1-2 selon la durée du retard."""
    t = t.copy()
    t["classe"] = t["classe"].str[3:]                         # '1. À l'heure' -> 'À l'heure'
    couleurs = [BLEU if c == "À l'heure" else GRIS if c == "1 à 3 j" else ROUGE for c in t["classe"]]
    fig = go.Figure(go.Bar(x=t["classe"], y=t["part_notes_1_2"], marker_color=couleurs,
                           text=[f"<b>{fr(v)} %</b>" for v in t["part_notes_1_2"]], textposition="outside",
                           customdata=t[["commandes", "note_moyenne"]],
                           hovertemplate="%{x}<br>%{y:.0f} % de notes 1–2 ★<br>note moyenne %{customdata[1]:.1f}"
                                         "<br>%{customdata[0]:,} commandes<extra></extra>"))
    fig.update_yaxes(visible=False, range=[0, 100])
    fig.update_xaxes(showline=False, ticks="")
    return mise_en_forme(fig, "Dès 4 jours de retard, deux clients sur trois sont mécontents",
                         "Part des commandes notées 1 ou 2 étoiles, selon le retard", hauteur=380)


def figure_semaines(s):
    """Q3 – line : taux de retard par semaine."""
    s = s.iloc[1:-1] if len(s) > 4 else s                  # 1re et dernière semaines incomplètes
    fig = go.Figure(go.Scatter(x=pd.to_datetime(s["semaine"]), y=s["taux_retard"], mode="lines",
                               line=dict(color=ROUGE, width=2.5), customdata=s["commandes"],
                               hovertemplate="Semaine du %{x|%d/%m/%Y}<br>%{y:.1f} % en retard"
                                             "<br>%{customdata} commandes<extra></extra>"))
    for debut, fin, texte in [("2017-11-20", "2017-12-04", "Black Friday"),
                              ("2018-02-05", "2018-03-26", "Févr. – mars 2018")]:
        fig.add_vrect(x0=debut, x1=fin, fillcolor=ROUGE, opacity=0.08, line_width=0,
                      annotation_text=texte, annotation_position="top left",
                      annotation_font=dict(size=10, color=ROUGE))
    reperes = pd.date_range("2017-01-01", "2018-08-01", freq="2MS")
    fig.update_xaxes(tickvals=reperes, ticktext=[f"{NOMS_MOIS[d.month - 1]} {d.year}" for d in reperes])
    fig.update_yaxes(ticksuffix=" %", rangemode="tozero", title=None)
    return mise_en_forme(fig, "Les retards explosent après Black Friday et en février – mars 2018",
                         "Part des commandes livrées en retard, par semaine d'achat", hauteur=360)


def figure_routes(r):
    """Q4 – heatmap : état du vendeur x état du client."""
    top = r.groupby("etat_vendeur")["commandes"].sum().nlargest(5).index
    r = r.copy()
    r["origine"] = r["etat_vendeur"].where(r["etat_vendeur"].isin(top), "Autres")
    g = r.assign(retards=r["taux_retard"] * r["commandes"] / 100).groupby(["origine", "etat_client"]) \
         .agg(commandes=("commandes", "sum"), retards=("retards", "sum")).reset_index()
    g["taux"] = g["retards"] / g["commandes"] * 100
    ordre_etats = [e for reg in REGIONS for e in init_db.REGIONS[reg] if e in set(g["etat_client"])]
    ordre_origine = list(top) + ["Autres"]
    taux = g.pivot(index="origine", columns="etat_client", values="taux").reindex(index=ordre_origine, columns=ordre_etats)
    nb = g.pivot(index="origine", columns="etat_client", values="commandes").reindex(index=ordre_origine, columns=ordre_etats).fillna(0)
    taux = taux.where(nb >= 30)
    fig = go.Figure(go.Heatmap(
        z=taux.values, x=taux.columns, y=taux.index, customdata=nb.values,
        colorscale=[[0, "#FFFFFF"], [0.25, "#F3D6D2"], [1, ROUGE]], zmin=0, zmax=25, xgap=2, ygap=2,
        colorbar=dict(ticksuffix=" %", thickness=10, len=0.8),
        text=[["" if np.isnan(v) else f"{v:.0f}" for v in ligne] for ligne in taux.values],
        texttemplate="%{text}", textfont=dict(size=10),
        hovertemplate="Vendeur %{y} → client %{x}<br>%{z:.1f} % en retard<br>%{customdata:.0f} commandes<extra></extra>"))
    # Nom des régions au-dessus des colonnes + un trait entre deux régions (le Nord-Est en rouge)
    position = 0
    for reg in REGIONS:
        nb_etats = len([e for e in init_db.REGIONS[reg] if e in ordre_etats])
        if nb_etats == 0:
            continue
        fig.add_annotation(x=position + (nb_etats - 1) / 2, y=1.02, yref="paper", yanchor="bottom", showarrow=False,
                           text=f"<b>{reg}</b>", font=dict(size=10, color=ROUGE if reg == "Nord-Est" else GRIS_FONCE))
        if position > 0:
            fig.add_vline(x=position - 0.5, line=dict(color=GRIS_FONCE, width=1.5))
        position += nb_etats
    fig.update_xaxes(showline=False, ticks="", title=dict(text="État du client (rangés par région)", font=dict(size=11)))
    fig.update_yaxes(autorange="reversed", showline=False, ticks="", title=dict(text="État du vendeur", font=dict(size=11)))
    fig = mise_en_forme(fig, "Le Nord-Est est en retard, quel que soit le vendeur",
                         "Ligne = état du vendeur · colonne = état du client · chiffre = % en retard · vide : moins de 30 commandes",
                         hauteur=380)
    fig.update_layout(margin=dict(t=110))
    return fig


def figure_regions(d):
    """Q5 – stacked bar : préparation + transport par région."""
    d = d.sort_values("transport")
    fig = go.Figure()
    fig.add_trace(go.Bar(y=d["region"], x=d["preparation"], orientation="h", name="Préparation vendeur",
                         marker_color=GRIS, text=[f"{fr(v, 1)} j" for v in d["preparation"]],
                         textposition="inside", insidetextanchor="middle", textfont=dict(color="white"),
                         hovertemplate="%{y}<br>Préparation : %{x:.1f} j<extra></extra>"))
    fig.add_trace(go.Bar(y=d["region"], x=d["transport"], orientation="h", name="Transport",
                         marker_color=ROUGE, text=[f"{fr(v, 1)} j" for v in d["transport"]],
                         textposition="inside", insidetextanchor="middle", textfont=dict(color="white"),
                         hovertemplate="%{y}<br>Transport : %{x:.1f} j<extra></extra>"))
    for _, l in d.iterrows():
        fig.add_annotation(x=l["preparation"] + l["transport"], y=l["region"], xshift=6, xanchor="left",
                           showarrow=False, font=dict(size=11, color=ROUGE), text=f"{fr(l['taux_retard'])} % en retard")
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_xaxes(title=dict(text="Délai moyen (jours)", font=dict(size=11)), range=[0, 34])
    fig.update_yaxes(showline=False, ticks="")
    mise_en_forme(fig, "C'est le transport qui fait la différence",
                  "Délai moyen par région du client", hauteur=380)
    fig.update_layout(showlegend=True, margin=dict(t=105),
                      legend=dict(orientation="h", x=0, y=1.13, title=None, traceorder="normal"))
    return fig


def figure_marge(e):
    """Q6 – scatter : marge de la promesse vs taux de retard, un point par état."""
    e = e[e["commandes"] >= 30].copy()
    taille = 8 + 45 * np.sqrt(e["ca"] / e["ca"].max())
    couleurs = np.where(e["region"] == "Nord-Est", ROUGE, np.where(e["region"] == "Nord", BLEU, GRIS))
    fig = go.Figure(go.Scatter(
        x=e["marge"], y=e["taux_retard"], mode="markers+text", text=e["etat"], textposition="top center",
        textfont=dict(size=10, color=GRIS_FONCE),
        marker=dict(size=taille, color=couleurs, opacity=0.8, line=dict(color="white", width=1)),
        customdata=np.stack([e["nom"], e["ca"] / 1e6, e["commandes"]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>marge %{x:.1f} j<br>%{y:.1f} % en retard"
                      "<br>CA %{customdata[1]:.2f} M R$ · %{customdata[2]} commandes<extra></extra>"))
    fig.update_xaxes(title=dict(text="Marge de la promesse : délai promis − délai réel (jours)", font=dict(size=11)))
    fig.update_yaxes(title=dict(text="% en retard", font=dict(size=11)), ticksuffix=" %", rangemode="tozero")
    return mise_en_forme(fig, "Moins de marge dans la promesse = plus de retards",
                         "Un point = un état (taille = CA) · rouge : Nord-Est · bleu : Nord", hauteur=420)


def tableau_priorites(e):
    """Q7 – table : les 8 états qui comptent le plus de commandes en retard."""
    total = e["en_retard"].sum()
    t = e.sort_values("en_retard", ascending=False).head(8).copy()
    t["part"] = t["en_retard"] / total * 100 if total else 0
    t["cumul"] = t["part"].cumsum()
    n = len(t)
    fond = ["#F3D6D2" if v > 10 else "white" for v in t["taux_retard"]]
    couleur = [ROUGE if v > 10 else GRIS_FONCE for v in t["taux_retard"]]
    fig = go.Figure(go.Table(
        columnwidth=[140, 75, 85, 70, 65, 50, 50, 75, 45],
        header=dict(values=["<b>État</b>", "<b>Région</b>", "<b>Commandes</b>", "<b>% retard</b>",
                            "<b>En retard</b>", "<b>Part</b>", "<b>Cumul</b>", "<b>CA en retard</b>", "<b>Note</b>"],
                    fill_color="#F3F4F6", line_color="#E5E7EB", align=["left", "left"] + ["right"] * 7,
                    font=dict(size=11, color="#1F2937"), height=30),
        cells=dict(values=[[f"<b>{nom}</b> ({code})" for nom, code in zip(t["nom"], t["etat"])], t["region"],
                           [fr(v) for v in t["commandes"]], [f"<b>{fr(v, 1)} %</b>" for v in t["taux_retard"]],
                           [fr(v) for v in t["en_retard"]], [f"{fr(v)} %" for v in t["part"]],
                           [f"{fr(v)} %" for v in t["cumul"]], [f"{fr(v / 1000)} k R$" for v in t["ca_retard"]],
                           [fr(v, 1) for v in t["note"]]],
                   fill_color=[["white"] * n] * 3 + [fond] + [["white"] * n] * 5,
                   font=dict(size=11, color=[[GRIS_FONCE] * n] * 3 + [couleur] + [[GRIS_FONCE] * n] * 5),
                   line_color="#E5E7EB", align=["left", "left"] + ["right"] * 7, height=28)))
    mise_en_forme(fig, "Par où commencer ? Les états qui comptent le plus de retards",
                  "Classés par nombre de commandes en retard · en rouge : plus de 10 % de retard", hauteur=360)
    fig.update_layout(margin=dict(t=85, l=10, r=10, b=10))
    return fig


def figure_plan(s, marge_nord_est, gain_rio, marge_pics):
    """Q8 – waterfall : combien de retards évite-t-on avec les 3 actions ?"""
    avant = int(s["avant"] or 0)
    gains = [int(s["action1"] or 0), int(s["action2"] or 0), int(s["action3"] or 0)]
    apres = avant - sum(gains)
    n = int(s["commandes"] or 0)
    fig = go.Figure(go.Waterfall(
        x=["Aujourd'hui", f"1. Promesse Nord-Est<br>(+{marge_nord_est} j)", f"2. Transport Rio<br>(−{gain_rio} j)",
           f"3. Pics<br>(+{marge_pics} j)", "Après les<br>3 actions"],
        measure=["absolute", "relative", "relative", "relative", "total"],
        y=[avant, -gains[0], -gains[1], -gains[2], apres],
        text=[fr(avant), f"−{fr(gains[0])}", f"−{fr(gains[1])}", f"−{fr(gains[2])}", fr(apres)],
        textposition="outside", textfont=dict(size=13),
        decreasing=dict(marker=dict(color=BLEU)), totals=dict(marker=dict(color=GRIS_FONCE)),
        connector=dict(line=dict(color=GRIS, width=1, dash="dot")),
        hovertemplate="%{x}<br>%{text} commandes<extra></extra>"))
    if n:
        fig.add_annotation(x=4, y=apres, yshift=42, showarrow=False, font=dict(size=12, color=GRIS_FONCE),
                           text=f"<b>{fr(apres / n * 100, 1)} % en retard</b><br>au lieu de {fr(avant / n * 100, 1)} %")
    fig.update_yaxes(visible=False, range=[0, max(avant, 1) * 1.2])
    fig.update_xaxes(showline=False, ticks="")
    part = sum(gains) / avant * 100 if avant else 0
    return mise_en_forme(fig, f"Trois actions pour éviter {fr(sum(gains))} retards (−{fr(part)} %)",
                         "Simulation : une commande « sauvée » est livrée avant la date promise · "
                         "réglez les hypothèses à droite", hauteur=420)


# =====================================================================
# 4. LA CARTE (comme au TP2), recalculée avec les filtres
# =====================================================================
def fiche(e, tranche):
    return f"""
    <div style="font-family: Arial; font-size: 13px; min-width: 200px;">
        <b style="font-size: 15px;">{e['nom']} ({e['etat']})</b><br>
        <span style="color: #6B7280;">{e['region']}</span>
        <hr style="margin: 6px 0;">
        Commandes : <b>{fr(e['commandes'])}</b><br>
        En retard : <b style="color: {COULEURS_TRANCHE[tranche]};">{fr(e['taux_retard'], 1)} %</b><br>
        Délai moyen : <b>{fr(e['delai'], 1)} jours</b><br>
        Note moyenne : <b>{fr(e['note'], 1)} / 5</b><br>
        Chiffre d'affaires : <b>{fr(e['ca'] / 1e6, 2)} M R$</b>
    </div>
    """


def carte_html(e, v):
    carte = folium.Map(location=[-14, -52], zoom_start=4)
    e = e.dropna(subset=["lat"]).copy()
    e["tranche"] = pd.cut(e["taux_retard"], bins=[-1, 5, 10, 100], labels=list(COULEURS_TRANCHE))
    for region in REGIONS:
        sel = e[e["region"] == region]
        if sel.empty:
            continue
        groupe = folium.FeatureGroup(name=f"Clients – {region}").add_to(carte)
        for _, l in sel.iterrows():
            folium.CircleMarker(
                location=[l["lat"], l["lon"]], radius=6 + 26 * np.sqrt(l["commandes"] / e["commandes"].max()),
                color="white", weight=1.5, fill=True, fill_color=COULEURS_TRANCHE[l["tranche"]], fill_opacity=0.85,
                tooltip=f"{l['etat']} : {fr(l['taux_retard'], 1)} % en retard",
                popup=folium.Popup(fiche(l, l["tranche"]), max_width=260)).add_to(groupe)

    groupe_v = folium.FeatureGroup(name="Vendeurs", show=False).add_to(carte)
    cluster = MarkerCluster(options={"disableClusteringAtZoom": 10}).add_to(groupe_v)
    for _, l in v.iterrows():          # une zone d'environ 10 km = un point
        folium.CircleMarker(location=[l["lat"], l["lon"]], radius=4, color=BLEU, weight=1,
                            fill=True, fill_color=BLEU, fill_opacity=0.7,
                            tooltip=f"{fr(l['vendeurs'])} vendeur(s) ({l['etat']}) · {fr(l['commandes'])} commandes"
                            ).add_to(cluster)
    folium.LayerControl(collapsed=False).add_to(carte)

    lignes = "".join(f"<div><span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
                     f"background:{c};margin-right:6px;'></span>{t}</div>" for t, c in COULEURS_TRANCHE.items())
    legende = f"""
    <div style="position: fixed; bottom: 20px; right: 10px; z-index: 9999; background: rgba(255,255,255,0.92);
                padding: 6px 9px; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.3);
                font-family: Arial; font-size: 11px; line-height: 1.5;">
      <b>Commandes en retard</b>{lignes}
      <div style="color:#6B7280;">Taille = nombre de commandes</div>
    </div>"""
    carte.get_root().html.add_child(folium.Element(legende))
    return carte.get_root().render()


# =====================================================================
# 5. LAYOUT : la page raconte une histoire en 3 chapitres
#    Le problème (1. C'est grave ? 2. Quand ? 3. Où ?) -> La cause (4. Pourquoi ?) -> La solution (5. Que faire ?)
# =====================================================================
app = Dash(__name__)
app.title = "Olist — Pourquoi les livraisons sont en retard ?"
server = app.server                    # pour gunicorn (Render)

app.index_string = """<!DOCTYPE html>
<html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
  html { scroll-behavior: smooth; }
  body { margin: 0; background: #F5F7FB; font-family: Arial, sans-serif; color: #1F2937; }
  .page { max-width: 1280px; margin: 0 auto; padding: 0 28px 40px; }
  /* En-tête : la mission */
  .entete { background: #0F1B2D; color: white; padding: 34px 0 30px; }
  .surtitre { font-size: 12px; letter-spacing: 0.12em; color: #93B4F5; text-transform: uppercase; }
  .entete h1 { font-size: 30px; margin: 8px 0 14px; }
  .citation { border-left: 4px solid #2457D6; padding: 4px 0 4px 16px; font-size: 16px; color: #E5E7EB; max-width: 820px; }
  .citation span { display: block; font-size: 12px; color: #9CA3AF; margin-top: 6px; }
  .sommaire { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 22px; }
  .sommaire a { color: white; text-decoration: none; font-size: 13px; padding: 7px 14px; border-radius: 20px;
                border: 1px solid #36507A; }
  .sommaire a:hover { background: #2457D6; border-color: #2457D6; }
  /* Barre des filtres : reste visible en haut quand on descend */
  .filtres { position: sticky; top: 0; z-index: 100; background: white; border-bottom: 1px solid #E5E7EB;
             box-shadow: 0 2px 6px rgba(0,0,0,0.06); }
  .filtres .page { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; padding-top: 10px; padding-bottom: 6px; }
  /* Chapitres et sections */
  .chapitre { display: flex; align-items: center; gap: 12px; margin: 40px 0 6px; }
  .chapitre-num { font-size: 12px; font-weight: bold; color: white; background: #2457D6; padding: 4px 10px; border-radius: 4px; }
  .chapitre-titre { font-size: 13px; font-weight: bold; letter-spacing: 0.12em; color: #2457D6; text-transform: uppercase; }
  .chapitre-ligne { flex: 1; height: 1px; background: #C9D6F2; }
  .section { margin-top: 22px; scroll-margin-top: 90px; }
  .question { display: flex; align-items: baseline; gap: 12px; }
  .question-num { font-size: 28px; font-weight: bold; color: #2457D6; }
  .question h2 { font-size: 22px; margin: 0; color: #0F1B2D; }
  .lecture { color: #4B5563; font-size: 14px; margin: 4px 0 0 40px; max-width: 900px; }
  .bloc { background: white; border-radius: 10px; padding: 10px; box-shadow: 0 1px 4px rgba(15,27,45,0.10); }
  .kpi { background: white; border-radius: 10px; padding: 12px 16px; box-shadow: 0 1px 4px rgba(15,27,45,0.10); flex: 1; }
  .kpi-etiquette { font-size: 11px; color: #6B7280; letter-spacing: 0.04em; }
  .kpi-valeur { font-size: 30px; font-weight: bold; margin: 6px 0 4px; }
  .kpi-detail { font-size: 12px; color: #4B5563; }
  .ligne { display: flex; gap: 16px; margin-top: 14px; }
  .ligne > .bloc { flex: 1; min-width: 0; }
  .action-titre { font-weight: bold; font-size: 14px; margin-top: 14px; }
  .action-detail { font-size: 12px; color: #6B7280; margin: 2px 0 6px; }
  /* Conclusion */
  .conclusion { background: #0F1B2D; color: white; border-radius: 12px; padding: 22px 26px; margin-top: 34px; }
  .conclusion h2 { margin: 0 0 14px; font-size: 20px; }
  .recos { display: flex; gap: 14px; flex-wrap: wrap; }
  .reco { flex: 1; min-width: 220px; background: #17294A; border-radius: 10px; padding: 14px 16px; }
  .reco b { color: #93B4F5; }
  .reco p { margin: 6px 0 0; font-size: 13px; color: #D1D5DB; }
  .pied { color: #6B7280; font-size: 12px; margin-top: 18px; }
</style></head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""

marques = {i: f"{NOMS_MOIS[m.month - 1]} {str(m.year)[2:]}" for i, m in enumerate(MOIS) if i % 3 == 0}

QUESTIONS = [("q1", "1", "C'est grave ?"), ("q2", "2", "Quand ?"), ("q3", "3", "Où ?"),
             ("q4", "4", "Pourquoi ?"), ("q5", "5", "Que faire ?")]


def chapitre(numero, titre):
    """Bandeau qui ouvre un chapitre de l'histoire."""
    return html.Div(className="chapitre", children=[
        html.Span(numero, className="chapitre-num"),
        html.Span(titre, className="chapitre-titre"),
        html.Div(className="chapitre-ligne")])


def section(ancre, numero, question, lecture, contenu):
    """Une question + une phrase pour lire les graphiques + les graphiques."""
    return html.Section(id=ancre, className="section", children=[
        html.Div(className="question", children=[html.Span(numero, className="question-num"), html.H2(question)]),
        html.P(lecture, className="lecture"),
        *contenu])


def bloc_graphique(id_graph, **style):
    return html.Div(className="bloc", style=style, children=[dcc.Graph(id=id_graph)])


app.layout = html.Div(children=[

    # ---------- En-tête : la mission ----------
    html.Header(className="entete", children=[html.Div(className="page", style={"paddingBottom": "0"}, children=[
        html.Div("Mission supply chain · Olist, Brésil", className="surtitre"),
        html.H1("Pourquoi les livraisons d'Olist arrivent-elles en retard ?"),
        html.Div(className="citation", children=[
            "« Nos clients nous donnent de mauvaises notes quand le colis arrive en retard. "
            "Pourquoi ces retards ? Et que nous proposez-vous ? »",
            html.Span("Le directeur des opérations d'Olist · 96 018 commandes livrées, janvier 2017 – août 2018 · "
                      "données publiques Olist (Kaggle)")]),
        html.Nav(className="sommaire", children=[html.A(f"{n}. {q}", href=f"#{a}") for a, n, q in QUESTIONS]),
    ])]),

    # ---------- Filtres (restent visibles en haut de l'écran) ----------
    html.Div(className="filtres", children=[html.Div(className="page", children=[
        html.Div([html.Label("Région du client :", style={"fontWeight": "bold", "fontSize": "13px"}),
                  dcc.Checklist(id="filtre-region", options=REGIONS, value=REGIONS, inline=True,
                                inputStyle={"marginRight": "5px", "marginLeft": "12px"})]),
        html.Div(style={"flex": "1", "minWidth": "320px"}, children=[
            html.Label("Période d'achat :", style={"fontWeight": "bold", "fontSize": "13px"}),
            dcc.RangeSlider(id="filtre-periode", min=0, max=len(MOIS) - 1, step=1,
                            value=[0, len(MOIS) - 1], marks=marques, allowCross=False,
                            allow_direct_input=False)]),
        html.Button("Refresh", id="bouton-actualiser", n_clicks=0,
                    style={"padding": "8px 16px", "borderRadius": "6px", "border": "none",
                           "background": "#2457D6", "color": "white", "cursor": "pointer"}),
        html.Div(id="info-donnees", style={"color": "#6B7280", "fontSize": "11px", "width": "100%"}),
    ])]),

    html.Main(className="page", children=[

        # ================= CHAPITRE I : LE PROBLÈME =================
        chapitre("I", "Le problème"),

        section("q1", "1", "C'est grave ?",
                "Peu de commandes sont en retard, mais un retard fait chuter la note du client.",
                [dcc.Loading(html.Div(id="kpis", className="ligne"), type="circle"),
                 html.Div(className="ligne", children=[bloc_graphique("graph-notes")])]),

        section("q2", "2", "Quand ?",
                "Les retards ne sont pas réguliers : ils montent pendant les pics de commandes.",
                [html.Div(className="ligne", children=[bloc_graphique("graph-semaines")])]),

        section("q3", "3", "Où ?",
                "La carte montre où sont les clients en retard. La heatmap croise l'état du vendeur et l'état du client.",
                [html.Div(className="ligne", children=[
                    html.Div(className="bloc", children=[
                        html.H3("Où sont les clients en retard ?", style={"margin": "4px 0 8px 6px", "fontSize": "15px"}),
                        html.Iframe(id="carte", style={"width": "100%", "height": "380px", "border": "none"})]),
                    bloc_graphique("graph-routes")])]),

        # ================= CHAPITRE II : LA CAUSE =================
        chapitre("II", "La cause"),

        section("q4", "4", "Pourquoi ?",
                "On sépare la préparation (le vendeur) et le transport (le transporteur), "
                "puis on regarde si la date promise laisse assez de marge.",
                [html.Div(className="ligne", children=[bloc_graphique("graph-regions"), bloc_graphique("graph-marge")])]),

        # ================= CHAPITRE III : LA SOLUTION =================
        chapitre("III", "La solution"),

        section("q5", "5", "Que faire ?",
                "On commence par les états qui ont le plus de retards, puis on simule trois actions. "
                "Bougez les curseurs pour tester d'autres hypothèses.",
                [html.Div(className="ligne", children=[bloc_graphique("graph-priorites")]),
                 html.Div(className="ligne", children=[
                     bloc_graphique("graph-plan", flex="2"),
                     html.Div(className="bloc", style={"flex": "1", "padding": "16px 20px"}, children=[
                         html.Div("1. Promesse réaliste pour le Nord-Est", className="action-titre"),
                         html.Div("Jours ajoutés à la date promise", className="action-detail"),
                         dcc.Slider(id="hyp-nord-est", min=0, max=10, step=1, value=5,
                                    marks={i: f"+{i}" for i in range(0, 11, 2)}, allow_direct_input=False),
                         html.Div("2. Transport plus rapide vers Rio", className="action-titre"),
                         html.Div("Jours gagnés sur le transport (changer ou renégocier le transporteur)",
                                  className="action-detail"),
                         dcc.Slider(id="hyp-rio", min=0, max=7, step=1, value=3,
                                    marks={i: f"−{i}" for i in range(0, 8)}, allow_direct_input=False),
                         html.Div("3. Préparer les pics (Black Friday, févr.–mars)", className="action-titre"),
                         html.Div("Jours de marge et capacité en plus pendant les pics", className="action-detail"),
                         dcc.Slider(id="hyp-pics", min=0, max=7, step=1, value=3,
                                    marks={i: f"+{i}" for i in range(0, 8)}, allow_direct_input=False),
                     ])])]),

        # ---------- Conclusion : la réponse au directeur ----------
        html.Div(className="conclusion", children=[
            html.H2("Ma réponse au directeur des opérations"),
            html.Div(className="recos", children=[
                html.Div(className="reco", children=[html.B("La cause"),
                    html.P("Ce n'est pas le vendeur : c'est le transport vers le Nord-Est et Rio, "
                           "et une date promise trop courte.")]),
                html.Div(className="reco", children=[html.B("Les actions"),
                    html.P("Promettre une date réaliste au Nord-Est, accélérer le transport vers Rio, "
                           "préparer les pics de commandes.")]),
                html.Div(className="reco", children=[html.B("Le résultat"),
                    html.P("Moins de retards, donc moins de clients mécontents : "
                           "la simulation ci-dessus donne le chiffre selon vos hypothèses.")]),
            ])]),

        html.P("Données : Brazilian E-Commerce Public Dataset by Olist (Kaggle) · base SQLite · Dash, Plotly, Folium · "
               "hébergé sur Render", className="pied"),
    ]),
])


# =====================================================================
# 6. CALCUL D'UNE VUE (avec cache)
#    Le serveur gratuit de Render est lent (0,1 CPU). On garde en mémoire les vues déjà calculées :
#    si on revient sur les mêmes filtres, la page s'affiche tout de suite.
#    Le cache est vidé à chaque Refresh (la base a pu changer).
# =====================================================================
@lru_cache(maxsize=64)
def calculer_vue(regions, i, j):
    """regions : tuple de régions ; i, j : indices des mois du curseur. Renvoie les 8 éléments de la page."""
    regions = list(regions)
    debut, fin = periode([i, j])
    k = db.kpis(regions, debut, fin)
    etats = db.par_etat(regions, debut, fin)
    return (cartes_kpi(k),
            figure_semaines(db.serie_semaines(regions, debut, fin)),
            figure_notes(db.notes_par_retard(regions, debut, fin)),
            figure_regions(db.delais_par_region(regions, debut, fin)),
            carte_html(etats, db.vendeurs(regions, debut, fin)),
            figure_marge(etats),
            figure_routes(db.routes(regions, debut, fin)),
            tableau_priorites(etats))


# Préchauffage : au démarrage, on calcule les vues les plus utilisées
# (la page d'accueil, puis les régions décochées une par une jusqu'au Nord-Est seul, et la période des pics)
TOUTE_LA_PERIODE = (0, len(MOIS) - 1)
for selection in [REGIONS, REGIONS[1:], REGIONS[2:], REGIONS[3:], ["Nord-Est"]]:
    calculer_vue(tuple(selection), *TOUTE_LA_PERIODE)
calculer_vue(tuple(REGIONS), 10, 14)          # novembre 2017 -> mars 2018


# =====================================================================
# 7. CALLBACK : les filtres OU le bouton Refresh mettent tout à jour
# =====================================================================
@app.callback(
    Output("kpis", "children"),
    Output("graph-semaines", "figure"),
    Output("graph-notes", "figure"),
    Output("graph-regions", "figure"),
    Output("carte", "srcDoc"),
    Output("graph-marge", "figure"),
    Output("graph-routes", "figure"),
    Output("graph-priorites", "figure"),
    Output("info-donnees", "children"),
    Output("filtre-region", "value"),
    Output("filtre-periode", "value"),
    Output("hyp-nord-est", "value"),
    Output("hyp-rio", "value"),
    Output("hyp-pics", "value"),
    Input("filtre-region", "value"),
    Input("filtre-periode", "value"),
    Input("bouton-actualiser", "n_clicks"),
)
def mettre_a_jour(regions, valeur_periode, n_clics):
    # Refresh : on recalcule les KPI à partir de la base, et on remet tous les filtres (et les hypothèses)
    hypotheses = (no_update, no_update, no_update)
    if ctx.triggered_id == "bouton-actualiser":
        n = db.calculer_faits()
        calculer_vue.cache_clear()            # la base a changé : on vide le cache
        INFO["texte"] = f"KPI recalculés depuis la base SQLite à {datetime.now():%H:%M:%S} · {fr(n)} commandes livrées"
        regions, valeur_periode = REGIONS, [0, len(MOIS) - 1]
        hypotheses = (5, 3, 3)

    regions = [r for r in REGIONS if r in (regions or [])]
    if not regions:
        vide = figure_vide("Cochez au moins une région")
        return ([], vide, vide, vide, "<p style='font-family:Arial'>Aucune région choisie.</p>",
                vide, vide, vide, INFO["texte"], regions, valeur_periode, *hypotheses)

    vue = calculer_vue(tuple(regions), valeur_periode[0], valeur_periode[1])
    return (*vue, INFO["texte"], regions, valeur_periode, *hypotheses)


# =====================================================================
# 8. CALLBACK DU PLAN D'ACTION : les filtres OU les hypothèses mettent à jour le waterfall
#    (callback séparé : bouger un curseur ne recalcule pas toute la page)
# =====================================================================
@app.callback(
    Output("graph-plan", "figure"),
    Input("filtre-region", "value"),
    Input("filtre-periode", "value"),
    Input("hyp-nord-est", "value"),
    Input("hyp-rio", "value"),
    Input("hyp-pics", "value"),
    Input("info-donnees", "children"),         # après un Refresh, la base a changé : on recalcule
)
def mettre_a_jour_plan(regions, valeur_periode, marge_nord_est, gain_rio, marge_pics, info):
    regions = [r for r in REGIONS if r in (regions or [])]
    if not regions:
        return figure_vide("Cochez au moins une région")
    debut, fin = periode(valeur_periode)
    s = db.simulation(regions, debut, fin, marge_nord_est, gain_rio, marge_pics)
    return figure_plan(s, marge_nord_est, gain_rio, marge_pics)


if __name__ == "__main__":
    app.run(debug=False)