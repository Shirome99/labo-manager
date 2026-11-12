from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, String, Integer, Date, DateTime, Text, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class User(Base):
    """Table users. Colonnes : id, nom, email, mot_de_passe, created_at, role, echecs_connexion, verrouille_jusqu."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nom: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    password: Mapped[str] = mapped_column("mot_de_passe", Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    # Sécurité des comptes (migration 016)
    echecs_connexion: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verrouille_jusqu: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def username(self) -> str:
        return self.nom


# ============================================================
# Modeles generes automatiquement depuis le schema reel
# (information_schema export). Ne pas editer a la main :
# chaque attribut est mappe sur le nom de colonne reel.
# ============================================================

class Echantillon(Base):
    __tablename__ = "echantillons"

    ordre: Mapped[int] = mapped_column("N° d'ordre", Integer, primary_key=True)
    num_echantillon: Mapped[str | None] = mapped_column('N° Echantillon', String, unique=True)
    date_reception: Mapped[datetime | None] = mapped_column('Date reception', DateTime)
    nature: Mapped[str | None] = mapped_column("Nature de l'échantillon", String)
    categorie: Mapped[str | None] = mapped_column("Catégorie de l'échantillon", String)
    type_echantillon: Mapped[int | None] = mapped_column("Type d'échantillon", Integer)
    stype_echantillon: Mapped[int | None] = mapped_column("S/type d'échantillon", Integer)
    espece_animale: Mapped[str | None] = mapped_column('Espèce animale', String)
    nbre_prlvmts_sma: Mapped[int | None] = mapped_column('Nbre Prlvmts SMA', Integer)
    nbre_prlvmts_scha: Mapped[int | None] = mapped_column('Nbre Prlvmts SCHA', Integer)
    nbre_prlvmts_ssa: Mapped[int | None] = mapped_column('Nbre Prlvmts SSA', Integer)
    num_lot: Mapped[str | None] = mapped_column('N° de lot', String)
    fabricant: Mapped[str | None] = mapped_column('Fabricant ou Propriétaire', String)
    organisme_preleveur: Mapped[str | None] = mapped_column('Organisme préleveur', String)
    ref_fiche_prelevement: Mapped[str | None] = mapped_column('Réf Fiche de prélèvement', String)
    sma: Mapped[str | None] = mapped_column('SMA', String)
    scha: Mapped[str | None] = mapped_column('SCHA', String)
    ssa: Mapped[str | None] = mapped_column('SSA', String)
    date_depot_ba_bacterio: Mapped[datetime | None] = mapped_column('Date dépôt BA Bactériologie', DateTime)
    date_depot_ba_chimie: Mapped[datetime | None] = mapped_column('Date dépôt BA Chimie', DateTime)
    date_depot_ba_sa: Mapped[datetime | None] = mapped_column('Date dépot BA SA', DateTime)
    date1_remise_rapport: Mapped[datetime | None] = mapped_column('Date 1 Remise Rapport', DateTime)
    date2_remise_rapport: Mapped[datetime | None] = mapped_column('Date 2 Remise Rapport', DateTime)
    payement: Mapped[str | None] = mapped_column('Payement', String)
    date_payement: Mapped[datetime | None] = mapped_column('Date de payement', DateTime)
    mode_paiement: Mapped[str | None] = mapped_column('Mode de paiement', String)
    montant_paye: Mapped[Decimal | None] = mapped_column('Montant payé', Numeric(12, 2))
    sortie_ma: Mapped[datetime | None] = mapped_column('Sortie MA', DateTime)
    sortie_ch: Mapped[datetime | None] = mapped_column('Sortie CH', DateTime)
    sortie_dc: Mapped[datetime | None] = mapped_column('Sortie Dc', DateTime)
    nb_para_ma: Mapped[str | None] = mapped_column('Nb Para MA', String)
    montant_total_ma: Mapped[str | None] = mapped_column('MONTANT TOTAL MA', String)
    nb_para_ch: Mapped[str | None] = mapped_column('Nb Para CH', String)
    montant_total_ch: Mapped[str | None] = mapped_column('MONTANT TOTAL CH', String)
    nb_para_sa: Mapped[str | None] = mapped_column('Nb Para SA', String)
    montant_total_sa: Mapped[str | None] = mapped_column('MONTANT TOTAL SA', String)
    total: Mapped[str | None] = mapped_column('TOTAL', String)
    num_quittance: Mapped[str | None] = mapped_column('N° QUITTANCE', String)
    date_quittance: Mapped[str | None] = mapped_column('DATE', String)
    statut: Mapped[str | None] = mapped_column(String)
    non_conformite: Mapped[str | None] = mapped_column(Text)
    # Non-conformités à la réception (migration 017)
    temperature_reception: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    nc_temperature: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nc_contenant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nc_quantite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nc_etiquetage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nc_delai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nc_autre: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decision_reception: Mapped[str | None] = mapped_column(String(25))
    motif_decision: Mapped[str | None] = mapped_column(Text)

    # Champs Rapport d'Essai (migration 003)
    client_nom: Mapped[str | None] = mapped_column('Nom du Client', String)
    adresse_client: Mapped[str | None] = mapped_column('Adresse du Client', String)
    date_prelevement: Mapped[datetime | None] = mapped_column('Date prelevement', DateTime)
    cadre_demande: Mapped[str | None] = mapped_column('Cadre de la demande', String)

class TraitementSMA(Base):
    __tablename__ = "traitement_sma"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    num_echantillon: Mapped[str] = mapped_column(
        String,
        ForeignKey("echantillons.N° Echantillon", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    num_ordre: Mapped[int | None] = mapped_column(Integer)
    nbre_prelevements: Mapped[int | None] = mapped_column(Integer)
    date_reception_ma: Mapped[date | None] = mapped_column(Date)
    lieu_stockage: Mapped[str | None] = mapped_column(String)
    date_revue_demande: Mapped[date | None] = mapped_column(Date)
    analyse_prevue_le: Mapped[date | None] = mapped_column(Date)
    delai_retenu_j: Mapped[int | None] = mapped_column(Integer)
    resp_reception: Mapped[str | None] = mapped_column(String)
    date_mise_en_analyse: Mapped[date | None] = mapped_column(Date)
    date_sortie_resultats: Mapped[date | None] = mapped_column(Date)
    date_rapport_essai: Mapped[date | None] = mapped_column(Date)
    observations: Mapped[str | None] = mapped_column(Text)
    conformite: Mapped[str | None] = mapped_column(String)
    declaration_conformite: Mapped[int | None] = mapped_column(Integer)
    commentaire_1: Mapped[str | None] = mapped_column(Text)
    commentaire_2: Mapped[str | None] = mapped_column(Text)
    erratum: Mapped[str | None] = mapped_column(Text)
    site_essai: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    saisi_par: Mapped[str | None] = mapped_column(String)
    valide_par: Mapped[str | None] = mapped_column(String)
    date_validation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    equipement_utilise: Mapped[str | None] = mapped_column(String)
    lot_reactif: Mapped[str | None] = mapped_column(String)

    # Champs Rapport d'Essai (migration 003)
    etat_echantillon: Mapped[str | None] = mapped_column(String)
    temperature_reception: Mapped[str | None] = mapped_column(String)

class TraitementSCHA(Base):
    __tablename__ = "traitement_scha"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    num_echantillon: Mapped[str] = mapped_column(
        String,
        ForeignKey("echantillons.N° Echantillon", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    num_ordre: Mapped[int | None] = mapped_column(Integer)
    nbre_prelevements: Mapped[int | None] = mapped_column(Integer)
    date_reception_cha: Mapped[date | None] = mapped_column(Date)
    nombre_unites_kg: Mapped[str | None] = mapped_column(String)
    analyse_prevue_le: Mapped[date | None] = mapped_column(Date)
    resp_reception: Mapped[str | None] = mapped_column(String)
    date_revue_demande: Mapped[date | None] = mapped_column(Date)
    lieu_stockage: Mapped[str | None] = mapped_column(String)
    delai_retenu_j: Mapped[int | None] = mapped_column(Integer)
    date_mise_en_analyse: Mapped[date | None] = mapped_column(Date)
    date_sortie_resultats: Mapped[date | None] = mapped_column(Date)
    date_re_cha: Mapped[date | None] = mapped_column(Date)
    observations: Mapped[str | None] = mapped_column(Text)
    categorie_echantillon: Mapped[str | None] = mapped_column(String)
    declaration_conformite: Mapped[str | None] = mapped_column(Text)
    commentaire_1: Mapped[str | None] = mapped_column(Text)
    commentaire_2: Mapped[str | None] = mapped_column(Text)
    conformite: Mapped[str | None] = mapped_column(String)
    erratum: Mapped[str | None] = mapped_column(Text)
    site_essai: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    saisi_par: Mapped[str | None] = mapped_column(String)
    valide_par: Mapped[str | None] = mapped_column(String)
    date_validation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    equipement_utilise: Mapped[str | None] = mapped_column(String)
    lot_reactif: Mapped[str | None] = mapped_column(String)

    # Champs Rapport d'Essai (migration 003)
    etat_echantillon: Mapped[str | None] = mapped_column(String)
    temperature_reception: Mapped[str | None] = mapped_column(String)

class TraitementSSA(Base):
    __tablename__ = "traitement_ssa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    num_echantillon: Mapped[str] = mapped_column(
        String,
        ForeignKey("echantillons.N° Echantillon", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    num_ordre: Mapped[int | None] = mapped_column(Integer)
    nbre_prelevements: Mapped[int | None] = mapped_column(Integer)
    espece_animale: Mapped[str | None] = mapped_column(String)
    date_reception_sa: Mapped[date | None] = mapped_column(Date)
    analyse_prevue_le: Mapped[date | None] = mapped_column(Date)
    resp_reception: Mapped[str | None] = mapped_column(String)
    date_revue_demande: Mapped[date | None] = mapped_column(Date)
    lieu_stockage: Mapped[str | None] = mapped_column(String)
    delai_retenu_j: Mapped[int | None] = mapped_column(Integer)
    date_mise_en_analyse: Mapped[date | None] = mapped_column(Date)
    date_sortie_resultats: Mapped[date | None] = mapped_column(Date)
    type_analyses: Mapped[str | None] = mapped_column(String)
    date_emission_re: Mapped[date | None] = mapped_column(Date)
    suspicion_clinique: Mapped[str | None] = mapped_column(Text)
    date_remise_re_sa: Mapped[date | None] = mapped_column(Date)
    observations: Mapped[str | None] = mapped_column(Text)
    categorie_echantillon: Mapped[str | None] = mapped_column(String)
    critere_interpretation: Mapped[str | None] = mapped_column(String)
    interpretation_resultats: Mapped[str | None] = mapped_column(Text)
    commentaire_1: Mapped[str | None] = mapped_column(Text)
    commentaire_2: Mapped[str | None] = mapped_column(Text)
    commentaire_3: Mapped[str | None] = mapped_column(Text)
    positivite: Mapped[str | None] = mapped_column(String)
    erratum: Mapped[str | None] = mapped_column(Text)
    site_essai: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    saisi_par: Mapped[str | None] = mapped_column(String)
    valide_par: Mapped[str | None] = mapped_column(String)
    date_validation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    equipement_utilise: Mapped[str | None] = mapped_column(String)
    lot_reactif: Mapped[str | None] = mapped_column(String)

    # Champs Rapport d'Essai (migration 003)
    etat_echantillon: Mapped[str | None] = mapped_column(String)
    temperature_reception: Mapped[str | None] = mapped_column(String)

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    horodatage: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    utilisateur: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40))
    table_cible: Mapped[str] = mapped_column(String(60))
    cle: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[str | None] = mapped_column(Text)


TRAITEMENT_MODELS = {
    "SMA": TraitementSMA,
    "SCHA": TraitementSCHA,
    "SSA": TraitementSSA,
}


# ============================================================
# Referentiels (migration 004) — blocs III et IV du rapport
# ============================================================

class RefCritereMicro(Base):
    __tablename__ = "ref_criteres_micro"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero_ordre: Mapped[int | None] = mapped_column(Integer)
    critere: Mapped[str | None] = mapped_column(String)
    domaine: Mapped[str | None] = mapped_column(String)
    type_echantillon: Mapped[str | None] = mapped_column(String)
    categorie_produit: Mapped[str] = mapped_column(String, nullable=False)
    parametre: Mapped[str | None] = mapped_column(String)
    n: Mapped[str | None] = mapped_column(String)
    c: Mapped[str | None] = mapped_column(String)
    m: Mapped[str | None] = mapped_column(String)
    grand_m: Mapped[str | None] = mapped_column(String)


class RefAnalyse(Base):
    __tablename__ = "ref_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero_ordre: Mapped[int | None] = mapped_column(Integer)
    nom_analyse: Mapped[str] = mapped_column(String, nullable=False)
    prix: Mapped[str | None] = mapped_column(String)
    reference_methode: Mapped[str | None] = mapped_column(String)
    delai_execution: Mapped[str | None] = mapped_column(String)
    type_analyse: Mapped[str | None] = mapped_column(String)
    section: Mapped[str | None] = mapped_column(String)
    code_prestation: Mapped[str | None] = mapped_column(String)


class RefCategorie(Base):
    __tablename__ = "ref_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    libelle: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    domaine: Mapped[str | None] = mapped_column(String)


class ResultatAnalyse(Base):
    __tablename__ = "resultats_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    num_echantillon: Mapped[str] = mapped_column(
        String, ForeignKey("echantillons.N° Echantillon", ondelete="CASCADE"), nullable=False
    )
    section: Mapped[str] = mapped_column(String, nullable=False)
    analyse_effectuee: Mapped[str | None] = mapped_column(String)
    reference_methode: Mapped[str | None] = mapped_column(String)
    volume_ensemence: Mapped[str | None] = mapped_column(String)
    nombre_analyses: Mapped[int | None] = mapped_column(Integer)
    date_analyse: Mapped[date | None] = mapped_column(Date)
    date_sortie: Mapped[date | None] = mapped_column(Date)
    rp1: Mapped[str | None] = mapped_column(String)
    rp2: Mapped[str | None] = mapped_column(String)
    rp3: Mapped[str | None] = mapped_column(String)
    rp4: Mapped[str | None] = mapped_column(String)
    rp5: Mapped[str | None] = mapped_column(String)
    saisi_par: Mapped[str | None] = mapped_column(String)
    cree_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
