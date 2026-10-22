# =====================================================================
# 1. IMPORTS & MODULES
# =====================================================================
import datetime
from zoneinfo import ZoneInfo
import io

import pandas as pd
import streamlit as st

# Imports du SDK Cadre Enterprise
import cadre_entreprise.auth as auth
import cadre_entreprise.ui as ui
from cadre_entreprise.database import supabase

# ReportLab pour l'exportation PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Configuration de la page Streamlit (Mode Large)
st.set_page_config(page_title="Gestion Budgétaire 2027", layout="wide", page_icon="💰")

# =====================================================================
# 2. SÉCURITÉ & AUTHENTIFICATION (VIA SDK)
# =====================================================================
if not auth.est_connecte():
    ui.afficher_ecran_login(nom_application="Gestion Budgétaire 2027", icone="💰")
    st.stop()

# Barre latérale standardisée (Profil + Lien vers le Portail Central)
ui.afficher_sidebar_standard()


# =====================================================================
# 3. FONCTIONS MÉTIER ET GÉNÉRATION PDF
# =====================================================================
def synchroniser_restant_budgets():
    """Recalcule dynamiquement les montants restants selon les devis acceptés."""
    try:
        budgets = (
            supabase.table("Budget")
            .select("id, montant_initial, montant_ajustement")
            .execute()
            .data
        )
        devis = (
            supabase.table("Devis").select("budget_id, montant, statut").execute().data
        )

        engagements_par_budget = {}
        for d in devis:
            if d.get("statut") == "Accepté":
                b_id = d.get("budget_id")
                m = float(d.get("montant") or 0)
                engagements_par_budget[b_id] = engagements_par_budget.get(b_id, 0.0) + m

        for b in budgets:
            b_id = b["id"]
            m_init = float(b.get("montant_initial") or 0)
            m_ajust = float(b.get("montant_ajustement") or 0)
            total_engagé = engagements_par_budget.get(b_id, 0.0)
            nouveau_restant = (m_init + m_ajust) - total_engagé

            supabase.table("Budget").update({"montant_restant": nouveau_restant}).eq(
                "id", b_id
            ).execute()
    except Exception as e:
        st.error(f"Erreur lors de la synchronisation des restants : {e}")


def generer_pdf_budget(df_synthese_brute, service_nom, annee):
    """
    Génère un rapport PDF officiel structuré par section (Fonctionnement / Investissement)
    avec sous-totaux par section et GRAND TOTAL GÉNÉRAL CONSOLIDÉ.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    elements = []
    styles = getSampleStyleSheet()

    # --- STYLES SUR-MESURE ---
    style_titre = ParagraphStyle(
        "TitreOfficiel",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=colors.HexColor("#1E3A8A"),
        spaceAfter=4,
    )
    style_sous_titre = ParagraphStyle(
        "SousTitreOfficiel",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#4B5563"),
    )
    style_section = ParagraphStyle(
        "TitreSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=10,
        spaceAfter=6,
    )
    style_entete_tab = ParagraphStyle(
        "EnteteTab",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.white,
        alignment=1,
    )
    style_cellule = ParagraphStyle(
        "CelluleText",
        fontName="Helvetica",
        fontSize=8,
        textColor=colors.HexColor("#1F2937"),
    )
    style_cellule_bold = ParagraphStyle(
        "CelluleTextBold",
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=colors.HexColor("#111827"),
    )
    style_cellule_montant = ParagraphStyle(
        "CelluleMontant",
        fontName="Helvetica",
        fontSize=8,
        textColor=colors.HexColor("#1F2937"),
        alignment=2,
    )
    style_cellule_montant_bold = ParagraphStyle(
        "CelluleMontantBold",
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=colors.HexColor("#111827"),
        alignment=2,
    )

    style_grand_total_label = ParagraphStyle(
        "GrandTotalLabel", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white
    )
    style_grand_total_montant = ParagraphStyle(
        "GrandTotalMontant",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.white,
        alignment=2,
    )

    # --- EN-TÊTE DU DOCUMENT ---
    elements.append(
        Paragraph(f"<b>PRÉPARATION BUDGÉTAIRE - ANNÉE {annee}</b>", style_titre)
    )
    fuseau_nc = ZoneInfo("Pacific/Noumea")
    date_jour = datetime.datetime.now(fuseau_nc).strftime("%d/%m/%Y à %H:%M")
    elements.append(
        Paragraph(
            f"Périmètre : <b>{service_nom}</b> | Édité le : {date_jour}",
            style_sous_titre,
        )
    )
    elements.append(Spacer(1, 8))
    elements.append(
        HRFlowable(
            width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=10
        )
    )

    def to_clean_float(val):
        if isinstance(val, (int, float)):
            return float(val)
        txt = str(val).replace("XPF", "").replace(" ", "").replace(",", "").strip()
        try:
            return float(txt)
        except ValueError:
            return 0.0

    def construire_tableau_section(df_section, titre_section):
        elements_section = []
        if df_section.empty:
            return elements_section

        elements_section.append(Paragraph(titre_section, style_section))

        en_tetes = [
            Paragraph("Service", style_entete_tab),
            Paragraph("Code LC", style_entete_tab),
            Paragraph("Libellé du Compte", style_entete_tab),
            Paragraph("Total Voté", style_entete_tab),
            Paragraph("Ajustements", style_entete_tab),
            Paragraph("Enveloppe Totale", style_entete_tab),
            Paragraph("Reste à Dépenser", style_entete_tab),
        ]

        donnees_pdf = [en_tetes]

        tot_initial = sum(to_clean_float(v) for v in df_section["Total_Initial"])
        tot_ajust = sum(to_clean_float(v) for v in df_section["Total_Ajustement"])
        tot_glob = sum(to_clean_float(v) for v in df_section["Enveloppe_Globale"])
        tot_rest = sum(to_clean_float(v) for v in df_section["Total_Restant"])

        for _, row in df_section.iterrows():
            m_init = to_clean_float(row.get("Total_Initial", 0))
            m_ajust = to_clean_float(row.get("Total_Ajustement", 0))
            m_glob = to_clean_float(row.get("Enveloppe_Globale", 0))
            m_rest = to_clean_float(row.get("Total_Restant", 0))

            donnees_pdf.append(
                [
                    Paragraph(str(row.get("service", "")), style_cellule),
                    Paragraph(str(row.get("code_lc", "")), style_cellule),
                    Paragraph(str(row.get("libelle", "")), style_cellule),
                    Paragraph(
                        f"{m_init:,.0f} XPF".replace(",", " "), style_cellule_montant
                    ),
                    Paragraph(
                        f"{m_ajust:,.0f} XPF".replace(",", " "), style_cellule_montant
                    ),
                    Paragraph(
                        f"{m_glob:,.0f} XPF".replace(",", " "), style_cellule_montant
                    ),
                    Paragraph(
                        f"{m_rest:,.0f} XPF".replace(",", " "), style_cellule_montant
                    ),
                ]
            )

        donnees_pdf.append(
            [
                Paragraph("<b>TOTAL SECTION</b>", style_cellule_bold),
                Paragraph("", style_cellule),
                Paragraph("", style_cellule),
                Paragraph(
                    f"{tot_initial:,.0f} XPF".replace(",", " "),
                    style_cellule_montant_bold,
                ),
                Paragraph(
                    f"{tot_ajust:,.0f} XPF".replace(",", " "),
                    style_cellule_montant_bold,
                ),
                Paragraph(
                    f"{tot_glob:,.0f} XPF".replace(",", " "), style_cellule_montant_bold
                ),
                Paragraph(
                    f"{tot_rest:,.0f} XPF".replace(",", " "), style_cellule_montant_bold
                ),
            ]
        )

        largeurs = [
            2.5 * cm,
            2.5 * cm,
            9.7 * cm,
            3.0 * cm,
            3.0 * cm,
            3.0 * cm,
            3.0 * cm,
        ]
        tableau = Table(donnees_pdf, colWidths=largeurs, repeatRows=1)

        style_table = TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E5E7EB")),
                ("SPAN", (0, -1), (2, -1)),
                ("TOPPADDING", (0, -1), (-1, -1), 6),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
            ]
        )

        for i in range(1, len(donnees_pdf) - 1):
            if i % 2 == 0:
                style_table.add(
                    "BACKGROUND", (0, i), (-1, i), colors.HexColor("#F9FAFB")
                )

        tableau.setStyle(style_table)
        elements_section.append(tableau)
        elements_section.append(Spacer(1, 10))
        return elements_section

    df_fonc = df_synthese_brute[df_synthese_brute["type_budget"] == "FONCTIONNEMENT"]
    df_inv = df_synthese_brute[df_synthese_brute["type_budget"] == "INVESTISSEMENT"]

    elements.extend(construire_tableau_section(df_fonc, "🔄 SECTION FONCTIONNEMENT"))
    elements.extend(construire_tableau_section(df_inv, "🏗️ SECTION INVESTISSEMENT"))

    if not df_synthese_brute.empty:
        gt_initial = sum(to_clean_float(v) for v in df_synthese_brute["Total_Initial"])
        gt_ajust = sum(to_clean_float(v) for v in df_synthese_brute["Total_Ajustement"])
        gt_glob = sum(to_clean_float(v) for v in df_synthese_brute["Enveloppe_Globale"])
        gt_rest = sum(to_clean_float(v) for v in df_synthese_brute["Total_Restant"])

        donnees_grand_total = [
            [
                Paragraph(
                    "📊 <b>TOTAL GÉNÉRAL CONSOLIDÉ (FONCTIONNEMENT + INVESTISSEMENT)</b>",
                    style_grand_total_label,
                ),
                Paragraph("", style_cellule),
                Paragraph("", style_cellule),
                Paragraph(
                    f"{gt_initial:,.0f} XPF".replace(",", " "),
                    style_grand_total_montant,
                ),
                Paragraph(
                    f"{gt_ajust:,.0f} XPF".replace(",", " "), style_grand_total_montant
                ),
                Paragraph(
                    f"{gt_glob:,.0f} XPF".replace(",", " "), style_grand_total_montant
                ),
                Paragraph(
                    f"{gt_rest:,.0f} XPF".replace(",", " "), style_grand_total_montant
                ),
            ]
        ]

        largeurs = [
            2.5 * cm,
            2.5 * cm,
            9.7 * cm,
            3.0 * cm,
            3.0 * cm,
            3.0 * cm,
            3.0 * cm,
        ]
        tab_grand_total = Table(donnees_grand_total, colWidths=largeurs)
        tab_grand_total.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1E3A8A")),
                    ("SPAN", (0, 0), (2, 0)),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#1E3A8A")),
                ]
            )
        )

        elements.append(Spacer(1, 5))
        elements.append(tab_grand_total)

    elements.append(Spacer(1, 15))
    elements.append(
        Paragraph("<b>Visa du Responsable Budgétaire :</b>", style_sous_titre)
    )

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# =====================================================================
# 4. INITIALISATION UTILISATEUR & PRÉPARATION SEMAINE/ANNÉE
# =====================================================================
user_actuel = auth.get_user_info()
role_utilisateur = str(user_actuel.get("role", "")).upper().strip()
service_utilisateur = user_actuel.get("service", "NON DEFINI")

# Sélecteur d'année dans la barre latérale (Sidebar)
with st.sidebar:
    st.divider()
    annee_active = st.selectbox(
        "📅 Année budgétaire :",
        options=[2026, 2027, 2028, 2029, 2030],
        index=1,  # Sélectionne 2027 par défaut
    )

# =====================================================================
# 5. DÉFINITION DES ONGLETS PAR RÔLE
# =====================================================================
if role_utilisateur == "ADMIN":
    onglet_budgets, onglet_devis, onglet_referentiel, onglet_admin = st.tabs(
        ["💰 Budgets", "📝 Devis", "⚙️ Référentiels", "👥 Administration"]
    )
else:
    onglet_budgets, onglet_devis = st.tabs(["💰 Budgets", "📝 Devis"])

# =====================================================================
# ONGLET 1 : LES BUDGETS
# =====================================================================
with onglet_budgets:
    col_titre, col_filtre = st.columns([2, 1])
    with col_titre:
        st.header(f"💰 Gestion Budgétaire ({annee_active})")

    with col_filtre:
        if role_utilisateur == "ADMIN":
            try:
                services_resp = (
                    supabase.table("Service")
                    .select("code_service")
                    .order("code_service")
                    .execute()
                )
                liste_services_bdd = [s["code_service"] for s in services_resp.data]
            except Exception:
                liste_services_bdd = []
            LISTE_SERVICES = ["TOUS"] + liste_services_bdd
            service_filtre = st.selectbox(
                "🎯 Filtrer par Service :", LISTE_SERVICES, index=0
            )
        else:
            service_filtre = service_utilisateur
            st.info(f"🔒 Périmètre restreint : **{service_filtre}**")

    try:
        reponse_lc = supabase.table("Ligne_Comptable").select("*").execute()
        donnees_lc_brutes = reponse_lc.data or []
        reponse_budgets = (
            supabase.table("Budget")
            .select("*")
            .eq("annee", annee_active)
            .order("code_lc")
            .execute()
        )
        donnees_budgets = reponse_budgets.data or []
    except Exception as erreur_lecture:
        st.error(f"Erreur de lecture de la base : {erreur_lecture}")
        donnees_lc_brutes, donnees_budgets = [], []

    if service_filtre != "TOUS":
        donnees_lc = [
            lc for lc in donnees_lc_brutes if lc.get("service") == service_filtre
        ]
    else:
        donnees_lc = donnees_lc_brutes

    dict_libelles = {lc["code_lc"]: lc["libelle"] for lc in donnees_lc}
    dict_types = {lc["code_lc"]: lc["type_budget"] for lc in donnees_lc}
    dict_services = {
        lc["code_lc"]: lc.get("service", "NON DÉFINI") for lc in donnees_lc_brutes
    }

    st.subheader(f"📊 Vue Consolidée ({service_filtre})")

    if len(donnees_budgets) > 0 and len(donnees_lc_brutes) > 0:
        df_budgets = pd.DataFrame(donnees_budgets)
        df_lc = pd.DataFrame(donnees_lc_brutes)
        df_complet = pd.merge(df_budgets, df_lc, on="code_lc", how="left")

        if service_filtre != "TOUS":
            df_complet = df_complet[df_complet["service"] == service_filtre]

        if not df_complet.empty:
            synthese = (
                df_complet.groupby(["service", "code_lc", "libelle", "type_budget"])
                .agg(
                    Total_Initial=("montant_initial", "sum"),
                    Total_Ajustement=("montant_ajustement", "sum"),
                    Total_Restant=("montant_restant", "sum"),
                )
                .reset_index()
            )

            synthese["Enveloppe_Globale"] = (
                synthese["Total_Initial"] + synthese["Total_Ajustement"]
            )

            synthese_affichage = synthese.copy()
            for col in [
                "Total_Initial",
                "Total_Ajustement",
                "Enveloppe_Globale",
                "Total_Restant",
            ]:
                synthese_affichage[col] = synthese_affichage[col].apply(
                    lambda x: f"{x:,.0f} XPF".replace(",", " ")
                )

            synthese_fonc = synthese_affichage[
                synthese_affichage["type_budget"] == "FONCTIONNEMENT"
            ].sort_values("code_lc")
            synthese_inv = synthese_affichage[
                synthese_affichage["type_budget"] == "INVESTISSEMENT"
            ].sort_values("code_lc")

            config_cols = {
                "service": "Service",
                "code_lc": "Code Ligne",
                "libelle": "Libellé",
                "type_budget": None,
                "Total_Initial": "Total Voté",
                "Total_Ajustement": "Ajustements",
                "Enveloppe_Globale": "ENVELOPPE GLOBALE",
                "Total_Restant": "RESTE À DÉPENSER",
            }

            if not synthese_fonc.empty:
                st.markdown("##### 🔄 SECTION FONCTIONNEMENT")
                st.dataframe(
                    synthese_fonc,
                    use_container_width=True,
                    hide_index=True,
                    column_config=config_cols,
                )

            if not synthese_inv.empty:
                st.markdown("##### 🏗️ SECTION INVESTISSEMENT")
                st.dataframe(
                    synthese_inv,
                    use_container_width=True,
                    hide_index=True,
                    column_config=config_cols,
                )

            st.markdown("##### 📄 Exportation Officielle")
            pdf_bytes = generer_pdf_budget(synthese, service_filtre, annee_active)
            st.download_button(
                label="📥 Télécharger la préparation budgétaire (PDF)",
                data=pdf_bytes,
                file_name=f"Budget_{service_filtre}_{annee_active}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.info(f"Aucun budget enregistré pour le service {service_filtre}.")
    else:
        st.info("Aucune donnée budgétaire disponible.")

    st.divider()

    st.subheader(f"➕ Déclarer un détail budgétaire pour {annee_active}")
    if len(dict_libelles) > 0:
        with st.form("formulaire_budget", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                st.number_input("Année", value=annee_active, disabled=True)
                code_lc_choisi = st.selectbox(
                    "Ligne Comptable",
                    options=list(dict_libelles.keys()),
                    format_func=lambda x: f"{x} - {dict_libelles[x]}",
                )
            with c2:
                categorie_saisie = st.text_input("Détail de la dépense")
                montant_saisi = st.number_input(
                    "Montant initial (XPF)", min_value=0.0, step=1000.0
                )
            btn_add_b = st.form_submit_button("Enregistrer la ligne")

        if btn_add_b:
            if categorie_saisie.strip() == "":
                st.warning("⚠️ Le détail est obligatoire.")
            else:
                nouveau_b = {
                    "annee": annee_active,
                    "code_lc": code_lc_choisi,
                    "categorie": categorie_saisie,
                    "montant_initial": montant_saisi,
                    "montant_ajustement": 0,
                    "montant_restant": montant_saisi,
                }
                try:
                    supabase.table("Budget").insert(nouveau_b).execute()
                    st.success("✅ Ligne ajoutée !")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erreur : {e}")
    else:
        st.warning(f"⚠️ Aucune Ligne Comptable pour le service {service_filtre}.")

    st.divider()

    st.subheader(f"📋 Détail des opérations ({service_filtre})")
    if len(donnees_budgets) > 0:
        for b in donnees_budgets:
            code = b["code_lc"]
            b["Service_Affichage"] = dict_services.get(code, "Inconnu")
            b["Libelle_Affichage"] = dict_libelles.get(code, "Inconnu")
            b["Type_Affichage"] = dict_types.get(code, "Inconnu")
            m_init, m_ajust, m_rest = (
                b.get("montant_initial") or 0,
                b.get("montant_ajustement") or 0,
                b.get("montant_restant") or 0,
            )
            b["Affichage_Initial"] = f"{m_init:,.0f}".replace(",", " ") + " XPF"
            b["Affichage_Ajustement"] = f"{m_ajust:,.0f}".replace(",", " ") + " XPF"
            b["Affichage_Total"] = (
                f"{(m_init + m_ajust):,.0f}".replace(",", " ") + " XPF"
            )
            b["Affichage_Restant"] = f"{m_rest:,.0f}".replace(",", " ") + " XPF"

        donnees_a_afficher = (
            [b for b in donnees_budgets if b["Service_Affichage"] == service_filtre]
            if service_filtre != "TOUS"
            else donnees_budgets
        )

        if len(donnees_a_afficher) > 0:
            with st.form("formulaire_edition"):
                st.data_editor(
                    donnees_a_afficher,
                    key="editeur_budget",
                    use_container_width=True,
                    hide_index=True,
                    num_rows="dynamic",
                    column_order=[
                        "Service_Affichage",
                        "code_lc",
                        "Libelle_Affichage",
                        "Type_Affichage",
                        "categorie",
                        "Affichage_Initial",
                        "Affichage_Ajustement",
                        "Affichage_Total",
                        "Affichage_Restant",
                    ],
                    column_config={
                        "Service_Affichage": st.column_config.TextColumn(
                            "Service", disabled=True
                        ),
                        "code_lc": st.column_config.SelectboxColumn(
                            "Code LC", options=list(dict_libelles.keys()), required=True
                        ),
                        "Libelle_Affichage": st.column_config.TextColumn(
                            "Libellé", disabled=True
                        ),
                        "Type_Affichage": st.column_config.TextColumn(
                            "Nature", disabled=True
                        ),
                        "Affichage_Initial": st.column_config.TextColumn(
                            "Voté", disabled=True
                        ),
                        "Affichage_Ajustement": st.column_config.TextColumn(
                            "Ajustement (Modifiable)"
                        ),
                        "Affichage_Total": st.column_config.TextColumn(
                            "Enveloppe Totale", disabled=True
                        ),
                        "Affichage_Restant": st.column_config.TextColumn(
                            "Reste à dépenser", disabled=True
                        ),
                    },
                )
                btn_maj_b = st.form_submit_button("💾 Sauvegarder les modifications")

            if btn_maj_b:
                try:
                    j_b = st.session_state["editeur_budget"]
                    if j_b.get("deleted_rows"):
                        for idx in j_b["deleted_rows"]:
                            supabase.table("Budget").delete().eq(
                                "id", donnees_a_afficher[int(idx)]["id"]
                            ).execute()
                    if j_b.get("edited_rows"):
                        for idx, modifs in j_b["edited_rows"].items():
                            id_mod = donnees_a_afficher[int(idx)]["id"]
                            if "Affichage_Ajustement" in modifs:
                                txt = (
                                    str(modifs["Affichage_Ajustement"])
                                    .replace(" ", "")
                                    .replace("XPF", "")
                                    .replace(",", "")
                                )
                                nouveau_ajust = float(txt)
                                ancien_ajust = (
                                    donnees_a_afficher[int(idx)].get(
                                        "montant_ajustement"
                                    )
                                    or 0
                                )
                                ancien_rest = (
                                    donnees_a_afficher[int(idx)].get("montant_restant")
                                    or 0
                                )
                                modifs["montant_ajustement"] = nouveau_ajust
                                modifs["montant_restant"] = ancien_rest + (
                                    nouveau_ajust - ancien_ajust
                                )
                                del modifs["Affichage_Ajustement"]
                            supabase.table("Budget").update(modifs).eq(
                                "id", id_mod
                            ).execute()
                    st.success("✅ Base mise à jour !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

# =====================================================================
# ONGLET 2 : LES DEVIS
# =====================================================================
with onglet_devis:
    st.header(f"📝 Gestion des Devis ({service_filtre})")
    try:
        reponse_devis = (
            supabase.table("Devis")
            .select("*")
            .eq("annee", annee_active)
            .order("id")
            .execute()
        )
        donnees_devis = reponse_devis.data or []
    except Exception as e:
        st.error(f"Erreur devis : {e}")
        donnees_devis = []

    options_budgets_filtres = {}
    ids_budgets_autorises = set()

    if len(donnees_budgets) > 0:
        for b in donnees_budgets:
            b_id = b["id"]
            code = b.get("code_lc", "SANS LC")
            srv = dict_services.get(code, "NON DÉFINI")
            if service_filtre == "TOUS" or srv == service_filtre:
                ids_budgets_autorises.add(b_id)
                lib = dict_libelles.get(code, "Inconnu")
                cat = b.get("categorie", "")
                r = float(b.get("montant_restant") or 0)
                options_budgets_filtres[b_id] = (
                    f"[{srv}] {code} - {lib} [{cat}] (Reste: {r:,.0f} XPF)"
                )

    devis_a_afficher = [
        d for d in donnees_devis if d.get("budget_id") in ids_budgets_autorises
    ]

    # --- FORMULAIRE D'AJOUT DE DEVIS AVEC DEPOSIT DU PDF ---
    st.subheader("➕ Enregistrer un devis")
    if len(options_budgets_filtres) > 0:
        with st.form("formulaire_devis", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                desc = st.text_input("Description / Objet")
                fourn = st.text_input("Fournisseur")
                email = st.text_input("Email Fournisseur")
                fichier_pdf = st.file_uploader(
                    "📎 Joindre le devis (PDF)", type=["pdf"]
                )
            with c2:
                num = st.text_input("N° Devis / Réf")
                b_id_choisi = st.selectbox(
                    "Ligne Comptable :",
                    options=list(options_budgets_filtres.keys()),
                    format_func=lambda x: options_budgets_filtres[x],
                )
                m_devis = st.number_input(
                    "Montant TTC (XPF)", min_value=0.0, step=1000.0
                )
                statut = st.selectbox("Statut", ["En attente", "Accepté", "Refusé"])

            btn_add_d = st.form_submit_button("Enregistrer le devis")

        if btn_add_d:
            if desc.strip() == "" or fourn.strip() == "":
                st.warning("⚠️ Description et fournisseur obligatoires.")
            else:
                pdf_url = None

                # Téléversement du PDF dans le Supabase Storage si présent
                if fichier_pdf is not None:
                    try:
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        nom_fichier = f"{annee_active}_{timestamp}_{fichier_pdf.name}"
                        contenu_fichier = fichier_pdf.read()

                        # Upload dans le bucket 'devis-pdfs'
                        supabase.storage.from_("devis-pdfs").upload(
                            file=contenu_fichier,
                            path=nom_fichier,
                            file_options={"content-type": "application/pdf"},
                        )

                        # Récupération de l'URL publique
                        pdf_url = supabase.storage.from_("devis-pdfs").get_public_url(
                            nom_fichier
                        )
                    except Exception as err_storage:
                        st.error(
                            f"❌ Erreur lors du téléversement du PDF : {err_storage}"
                        )

                nouveau_d = {
                    "annee": annee_active,
                    "budget_id": b_id_choisi,
                    "description": desc.strip(),
                    "fournisseur": fourn.strip(),
                    "email_fournisseur": email.strip(),
                    "numero": num.strip(),
                    "montant": m_devis,
                    "statut": statut,
                    "pdf_url": pdf_url,  # Sauvegarde du lien
                }
                try:
                    supabase.table("Devis").insert(nouveau_d).execute()
                    synchroniser_restant_budgets()
                    st.success("✅ Devis enregistré avec succès !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

    st.divider()

    # --- HISTORIQUE ET GESTION DES PDF EN LIGNE ---
    st.subheader(f"📋 Historique des Devis ({service_filtre})")
    if len(devis_a_afficher) > 0:
        for d in devis_a_afficher:
            d["Affichage_Montant"] = (
                f"{float(d.get('montant') or 0):,.0f}".replace(",", " ") + " XPF"
            )
            d["Budget_Affichage"] = options_budgets_filtres.get(
                d.get("budget_id"), "Inconnu"
            )

        with st.form("edition_devis"):
            st.data_editor(
                devis_a_afficher,
                key="editeur_devis",
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_order=[
                    "description",
                    "fournisseur",
                    "email_fournisseur",
                    "numero",
                    "Budget_Affichage",
                    "Affichage_Montant",
                    "statut",
                    "pdf_url",  # Ajout de la colonne URL
                ],
                column_config={
                    "Budget_Affichage": st.column_config.TextColumn(
                        "Imputation", disabled=True
                    ),
                    "statut": st.column_config.SelectboxColumn(
                        "Statut", options=["En attente", "Accepté", "Refusé"]
                    ),
                    "pdf_url": st.column_config.LinkColumn(
                        "Document PDF",
                        display_text="👁️ Voir PDF",
                        validate="^https://.*",
                    ),
                },
            )
            btn_maj_d = st.form_submit_button("💾 Sauvegarder les devis")

        if btn_maj_d:
            try:
                j_d = st.session_state["editeur_devis"]
                if j_d.get("deleted_rows"):
                    for idx in j_d["deleted_rows"]:
                        supabase.table("Devis").delete().eq(
                            "id", devis_a_afficher[int(idx)]["id"]
                        ).execute()
                if j_d.get("edited_rows"):
                    for idx, modifs in j_d["edited_rows"].items():
                        id_m = devis_a_afficher[int(idx)]["id"]
                        if "Affichage_Montant" in modifs:
                            modifs["montant"] = float(
                                str(modifs["Affichage_Montant"])
                                .replace(" ", "")
                                .replace("XPF", "")
                                .replace(",", "")
                            )
                            del modifs["Affichage_Montant"]
                        supabase.table("Devis").update(modifs).eq("id", id_m).execute()
                synchroniser_restant_budgets()
                st.success("✅ Devis mis à jour !")
                st.rerun()
            except Exception as e:
                st.error(f"Erreur : {e}")

        # --- GESTION (AJOUT / MODIFICATION / SUPPRESSION) DES PDFS EXISTANTS ---
        st.divider()
        st.markdown("#### ⚙️ Gestion des pièces jointes (PDF)")

        for devis in devis_a_afficher:
            d_id = devis.get("id")
            d_desc = devis.get("description", "Devis")
            d_fourn = devis.get("fournisseur", "")
            d_url = devis.get("pdf_url")

            with st.expander(f"📄 {d_desc} - {d_fourn} (ID: {d_id})"):
                c_statut, c_action = st.columns([2, 3])

                with c_statut:
                    if d_url:
                        st.success("Fichier joint disponible")
                        st.link_button(
                            "👁️ Ouvrir le PDF", d_url, use_container_width=True
                        )
                    else:
                        st.warning("Aucun fichier joint")

                with c_action:
                    # Remplacement / Ajout
                    nouveau_pdf = st.file_uploader(
                        "Téléverser / Remplacer le PDF",
                        type=["pdf"],
                        key=f"file_up_{d_id}",
                    )

                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        if (
                            st.button("💾 Enregistrer le PDF", key=f"btn_save_{d_id}")
                            and nouveau_pdf
                        ):
                            try:
                                timestamp = datetime.datetime.now().strftime(
                                    "%Y%m%d_%H%M%S"
                                )
                                nom_fichier = (
                                    f"{annee_active}_{timestamp}_{nouveau_pdf.name}"
                                )
                                supabase.storage.from_("devis-pdfs").upload(
                                    file=nouveau_pdf.read(),
                                    path=nom_fichier,
                                    file_options={"content-type": "application/pdf"},
                                )
                                new_url = supabase.storage.from_(
                                    "devis-pdfs"
                                ).get_public_url(nom_fichier)

                                supabase.table("Devis").update({"pdf_url": new_url}).eq(
                                    "id", d_id
                                ).execute()
                                st.success("PDF mis à jour !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur lors de l'envoi : {e}")

                    with col_b2:
                        if d_url and st.button(
                            "🗑️ Supprimer le PDF", key=f"btn_del_{d_id}"
                        ):
                            try:
                                supabase.table("Devis").update({"pdf_url": None}).eq(
                                    "id", d_id
                                ).execute()
                                st.success("PDF dissocié du devis !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur lors de la suppression : {e}")

        # --- LISTE DES LIENS DE CONSULTATION PDF ---
        st.markdown("#### 📄 Documents PDF associés")
        for d in devis_a_afficher:
            url = d.get("pdf_url")
            if url:
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.write(
                        f"📌 **{d.get('description')}** ({d.get('fournisseur')}) - {d.get('numero') or 'Sans N°'}"
                    )
                with col_btn:
                    st.link_button("👁️ Ouvrir le PDF", url, use_container_width=True)

# =====================================================================
# ONGLET 3 : RÉFÉRENTIELS (RÉSERVÉ ADMIN)
# =====================================================================
if role_utilisateur == "ADMIN":
    with onglet_referentiel:
        st.header("⚙️ Gestion des Référentiels")

        st.subheader("1. Référentiel des Services")
        with st.form("form_service", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                code_s = st.text_input("Code Service (ex: SANL)").upper().strip()
            with c2:
                nom_s = st.text_input("Libellé du Service")
            btn_add_s = st.form_submit_button("➕ Créer le service")

        if btn_add_s:
            if code_s != "" and nom_s != "":
                try:
                    supabase.table("Service").insert(
                        {"code_service": code_s, "nom_service": nom_s}
                    ).execute()
                    st.success("✅ Service créé !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

        st.divider()
        st.subheader("2. Nomenclature Comptable (Lignes LC)")
        try:
            liste_s = [
                s["code_service"]
                for s in (
                    supabase.table("Service").select("code_service").execute().data
                    or []
                )
            ]
        except Exception:
            liste_s = []

        with st.form("form_lc", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                code_lc = st.text_input("Code LC (ex: LC6000)").upper().strip()
            with c2:
                lib_lc = st.text_input("Libellé Officiel")
            with c3:
                type_lc = st.selectbox("Nature", ["FONCTIONNEMENT", "INVESTISSEMENT"])
            with c4:
                srv_lc = st.selectbox("Service Propriétaire", options=liste_s)
            btn_add_lc = st.form_submit_button("➕ Créer la Ligne")

        if btn_add_lc:
            if code_lc != "" and lib_lc != "":
                try:
                    supabase.table("Ligne_Comptable").insert(
                        {
                            "code_lc": code_lc,
                            "libelle": lib_lc,
                            "type_budget": type_lc,
                            "service": srv_lc,
                        }
                    ).execute()
                    st.success("✅ Ligne Comptable créée !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

# =====================================================================
# ONGLET 4 : ADMINISTRATION DES COMPTES (RÉSERVÉ ADMIN)
# =====================================================================
if role_utilisateur == "ADMIN":
    with onglet_admin:
        st.header("👥 Gestion des Comptes Utilisateurs")
        try:
            services_bdd = [
                s["code_service"]
                for s in (
                    supabase.table("Service").select("code_service").execute().data
                    or []
                )
            ]
        except Exception:
            services_bdd = []
        options_services_user = ["TOUS"] + services_bdd

        st.subheader("➕ Créer un nouvel utilisateur")
        with st.form("form_creer_utilisateur", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                nouveau_login = st.text_input("Identifiant / Login").lower().strip()
                nouveau_mdp = st.text_input("Mot de passe", type="password")
            with c2:
                nouveau_nom = st.text_input("Nom / Prénom / Fonction")
                nouveau_role = st.selectbox("Rôle", ["USER", "ADMIN"])
            with c3:
                nouveau_service = st.selectbox(
                    "Service Attribué", options=options_services_user
                )
            bouton_creer_user = st.form_submit_button("➕ Créer le compte")

        if bouton_creer_user:
            if nouveau_login == "" or nouveau_mdp == "" or nouveau_nom == "":
                st.warning("⚠️ Tous les champs sont obligatoires.")
            else:
                # Utilisation du hachage via le SDK Cadre Enterprise
                mdp_securise = auth.hacher_mot_de_passe(nouveau_mdp)
                nouvel_u = {
                    "login": nouveau_login,
                    "mdp": mdp_securise,
                    "nom": nouveau_nom,
                    "role": nouveau_role,
                    "service": nouveau_service,
                }
                try:
                    supabase.table("Utilisateur").insert(nouvel_u).execute()
                    st.success(f"✅ Compte '{nouveau_login}' créé !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

        st.divider()

        st.subheader("📋 Liste des Comptes Actifs")
        try:
            donnees_users = (
                supabase.table("Utilisateur").select("*").order("login").execute().data
                or []
            )
        except Exception:
            donnees_users = []

        if len(donnees_users) > 0:
            with st.form("form_edition_utilisateurs"):
                st.data_editor(
                    donnees_users,
                    key="editeur_utilisateurs",
                    use_container_width=True,
                    hide_index=True,
                    num_rows="dynamic",
                    column_order=["login", "mdp", "nom", "role", "service"],
                    column_config={
                        "login": st.column_config.TextColumn("Login", disabled=True),
                        "mdp": st.column_config.TextColumn("Mot de passe (Modifiable)"),
                        "role": st.column_config.SelectboxColumn(
                            "Rôle", options=["USER", "ADMIN"], required=True
                        ),
                        "service": st.column_config.SelectboxColumn(
                            "Service", options=options_services_user, required=True
                        ),
                    },
                )
                bouton_maj_users = st.form_submit_button(
                    "💾 Sauvegarder les modifications"
                )

            if bouton_maj_users:
                try:
                    j_u = st.session_state["editeur_utilisateurs"]
                    if j_u.get("deleted_rows"):
                        for idx in j_u["deleted_rows"]:
                            supabase.table("Utilisateur").delete().eq(
                                "login", donnees_users[int(idx)]["login"]
                            ).execute()
                    if j_u.get("edited_rows"):
                        for idx, modifs in j_u["edited_rows"].items():
                            log_mod = donnees_users[int(idx)]["login"]
                            if "mdp" in modifs and modifs["mdp"].strip() != "":
                                modifs["mdp"] = auth.hacher_mot_de_passe(modifs["mdp"])
                            supabase.table("Utilisateur").update(modifs).eq(
                                "login", log_mod
                            ).execute()
                    st.success("✅ Comptes mis à jour !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")
