from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

OuiNon = Literal["Yes", "No"]
Role = Literal["admin", "responsable", "sma", "scha", "ssa", "user"]
Decision = Literal["Accepté", "Accepté sous réserve", "Refusé"]


# ---------- Auth / Utilisateurs ----------
class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: Role
    email: str | None = None
    verrouille_jusqu: datetime | None = None


class ConnexionOut(UserOut):
    """Réponse de connexion : jeton `Authorization: Bearer` (front sur un autre site) et sa durée (s)."""
    jeton: str
    jeton_duree: int


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1)   # règle détaillée : security.exiger_mot_de_passe_conforme
    role: Role = "user"
    email: str | None = None


class RoleUpdate(BaseModel):
    role: Role


class MotDePasseChange(BaseModel):
    actuel: str
    nouveau: str


class MotDePasseReset(BaseModel):
    nouveau: str


# ---------- Echantillons (aligne sur les 39 colonnes reelles) ----------
class EchantillonIn(BaseModel):
    num_echantillon: str | None = None
    date_reception: datetime | None = None
    nature: str | None = None
    categorie: str | None = None
    type_echantillon: int | None = None
    stype_echantillon: int | None = None
    espece_animale: str | None = None
    nbre_prlvmts_sma: int | None = None
    nbre_prlvmts_scha: int | None = None
    nbre_prlvmts_ssa: int | None = None
    num_lot: str | None = None
    fabricant: str | None = None
    organisme_preleveur: str | None = None
    ref_fiche_prelevement: str | None = None
    sma: OuiNon = "No"
    scha: OuiNon = "No"
    ssa: OuiNon = "No"
    date_depot_ba_bacterio: datetime | None = None
    date_depot_ba_chimie: datetime | None = None
    date_depot_ba_sa: datetime | None = None
    date1_remise_rapport: datetime | None = None
    date2_remise_rapport: datetime | None = None
    payement: str | None = None
    date_payement: datetime | None = None
    mode_paiement: str | None = None
    montant_paye: Decimal | None = None
    sortie_ma: datetime | None = None
    sortie_ch: datetime | None = None
    sortie_dc: datetime | None = None
    nb_para_ma: str | None = None
    montant_total_ma: str | None = None
    nb_para_ch: str | None = None
    montant_total_ch: str | None = None
    nb_para_sa: str | None = None
    montant_total_sa: str | None = None
    total: str | None = None
    num_quittance: str | None = None
    date_quittance: str | None = None
    non_conformite: str | None = None
    # Non-conformités à la réception (migration 017)
    temperature_reception: Decimal | None = None
    nc_temperature: bool = False
    nc_contenant: bool = False
    nc_quantite: bool = False
    nc_etiquetage: bool = False
    nc_delai: bool = False
    nc_autre: bool = False
    decision_reception: Decision | None = None
    motif_decision: str | None = None
    client_nom: str | None = None
    adresse_client: str | None = None
    date_prelevement: datetime | None = None
    cadre_demande: str | None = None

class EchantillonOut(EchantillonIn):
    ordre: int
    num_echantillon: str | None = None
    statut: str | None = None

    class Config:
        from_attributes = True


# ---------- Traitements (3 structures distinctes, generees) ----------
class TraitementSMAIn(BaseModel):
    num_echantillon: str
    num_ordre: int | None = None
    nbre_prelevements: int | None = None
    date_reception_ma: date | None = None
    lieu_stockage: str | None = None
    date_revue_demande: date | None = None
    analyse_prevue_le: date | None = None
    delai_retenu_j: int | None = None
    resp_reception: str | None = None
    date_mise_en_analyse: date | None = None
    date_sortie_resultats: date | None = None
    date_rapport_essai: date | None = None
    observations: str | None = None
    conformite: str | None = None
    declaration_conformite: int | None = None
    commentaire_1: str | None = None
    commentaire_2: str | None = None
    erratum: str | None = None
    site_essai: str | None = None
    equipement_utilise: str | None = None
    lot_reactif: str | None = None
    etat_echantillon: str | None = None
    temperature_reception: str | None = None

class TraitementSMAOut(TraitementSMAIn):
    id: int
    saisi_par: str | None = None
    valide_par: str | None = None
    date_validation: datetime | None = None

    class Config:
        from_attributes = True

class TraitementSCHAIn(BaseModel):
    num_echantillon: str
    num_ordre: int | None = None
    nbre_prelevements: int | None = None
    date_reception_cha: date | None = None
    nombre_unites_kg: str | None = None
    analyse_prevue_le: date | None = None
    resp_reception: str | None = None
    date_revue_demande: date | None = None
    lieu_stockage: str | None = None
    delai_retenu_j: int | None = None
    date_mise_en_analyse: date | None = None
    date_sortie_resultats: date | None = None
    date_re_cha: date | None = None
    observations: str | None = None
    categorie_echantillon: str | None = None
    declaration_conformite: str | None = None
    commentaire_1: str | None = None
    commentaire_2: str | None = None
    conformite: str | None = None
    erratum: str | None = None
    site_essai: str | None = None
    equipement_utilise: str | None = None
    lot_reactif: str | None = None
    etat_echantillon: str | None = None
    temperature_reception: str | None = None

class TraitementSCHAOut(TraitementSCHAIn):
    id: int
    saisi_par: str | None = None
    valide_par: str | None = None
    date_validation: datetime | None = None

    class Config:
        from_attributes = True

class TraitementSSAIn(BaseModel):
    num_echantillon: str
    num_ordre: int | None = None
    nbre_prelevements: int | None = None
    espece_animale: str | None = None
    date_reception_sa: date | None = None
    analyse_prevue_le: date | None = None
    resp_reception: str | None = None
    date_revue_demande: date | None = None
    lieu_stockage: str | None = None
    delai_retenu_j: int | None = None
    date_mise_en_analyse: date | None = None
    date_sortie_resultats: date | None = None
    type_analyses: str | None = None
    date_emission_re: date | None = None
    suspicion_clinique: str | None = None
    date_remise_re_sa: date | None = None
    observations: str | None = None
    categorie_echantillon: str | None = None
    critere_interpretation: str | None = None
    interpretation_resultats: str | None = None
    commentaire_1: str | None = None
    commentaire_2: str | None = None
    commentaire_3: str | None = None
    positivite: str | None = None
    erratum: str | None = None
    site_essai: str | None = None
    equipement_utilise: str | None = None
    lot_reactif: str | None = None
    etat_echantillon: str | None = None
    temperature_reception: str | None = None

class TraitementSSAOut(TraitementSSAIn):
    id: int
    saisi_par: str | None = None
    valide_par: str | None = None
    date_validation: datetime | None = None

    class Config:
        from_attributes = True

