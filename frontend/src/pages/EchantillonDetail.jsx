import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Alert, App, Button, Card, Col, Descriptions, Empty, Flex, Form, Input, Modal, Row, Space, Spin, Steps,
  Table, Tag, Tooltip, Typography,
} from "antd";
import {
  ArrowLeftOutlined, ArrowRightOutlined, DownloadOutlined, EditOutlined, FilePdfOutlined, PrinterOutlined,
} from "@ant-design/icons";
import { ErreurChargement } from "../components/etats";
import FacturationEchantillon from "../components/FacturationEchantillon";
import { api } from "../api/client";
import BoutonFichier from "../components/BoutonFichier";
import {
  DecisionTag, NON_CONFORMITES, PaiementTag, ROLES_GLOBAUX, STATUTS, SectionTag, StatutTag, estResponsable,
} from "../components/ui";

const LIBELLE_SECTION = { SMA: "Microbiologie Alimentaire", SCHA: "Chimie / Hygiène", SSA: "Santé Animale" };
const fmtDate = (d) => (d ? new Date(d).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "—");

// Historique des rapports émis (toutes versions, PDF figés)
function HistoriqueRapports({ rapports }) {
  const colonnes = [
    { title: "Section", dataIndex: "section", key: "section", width: 80, render: (s) => <SectionTag code={s} /> },
    { title: "Numéro", dataIndex: "numero", key: "numero", render: (v) => <span className="mono">{v}</span> },
    { title: "Version", dataIndex: "version", key: "version", width: 70, align: "center" },
    { title: "Émis le", dataIndex: "date_emission", key: "date", render: fmtDate },
    { title: "Émis par", dataIndex: "emis_par", key: "par" },
    {
      title: "Empreinte SHA-256", dataIndex: "sha256", key: "sha",
      render: (v) => (
        <Typography.Text className="mono" copyable={{ text: v, tooltips: ["Copier", "Copié"] }}>
          {v.slice(0, 12)}…
        </Typography.Text>
      ),
    },
    {
      title: "Statut", key: "statut",
      render: (_, r) => (
        <Space size={4} wrap>
          {r.statut === "valide" ? <Tag color="green">Valide</Tag> : <Tag>Annulé</Tag>}
          {r.statut === "valide" && r.erratum_motif && (
            <Tooltip title={`Motif : ${r.erratum_motif}`}><Tag color="gold">Erratum en cours</Tag></Tooltip>
          )}
          {r.motif && <Tooltip title={`Motif : ${r.motif}`}><Tag color="blue">Remplace une version</Tag></Tooltip>}
        </Space>
      ),
    },
    {
      title: "", key: "pdf", align: "right", width: 60,
      render: (_, r) => (
        <Tooltip title="Télécharger cette version">
          <BoutonFichier type="text" size="small" icon={<DownloadOutlined />} aria-label="Télécharger"
                         url={api.urlRapportVersion(r.id)} />
        </Tooltip>
      ),
    },
  ];
  return (
    <Card size="small" title="Rapports d'essai émis" className="bloc">
      <Table size="small" rowKey="id" pagination={false} columns={colonnes} dataSource={rapports}
             locale={{ emptyText: "Aucun rapport émis." }} />
    </Card>
  );
}

// Lots de réactifs / milieux cités par les fiches de traitement (traçabilité, tâche 20)
function LotsUtilises({ lots }) {
  return (
    <Card size="small" title="Réactifs et milieux utilisés" className="bloc">
      <Table size="small" rowKey={(r) => `${r.section}-${r.code}`} pagination={false} dataSource={lots}
             columns={[
               { title: "Section", dataIndex: "section", width: 80, render: (s) => <SectionTag code={s} /> },
               { title: "Code", dataIndex: "code", width: 120, render: (v, r) => (r.connu ? <Link className="mono" to={`/reactifs?lot=${r.id}`}>{v}</Link> : <span className="mono">{v}</span>) },
               { title: "Produit", dataIndex: "produit", render: (v, r) => (r.connu ? v : <Typography.Text type="secondary">Lot non référencé</Typography.Text>) },
               { title: "Catégorie", dataIndex: "categorie", width: 140, render: (v) => v || "—" },
               { title: "N° de lot", dataIndex: "numero_lot", width: 130, render: (v) => (v ? <span className="mono">{v}</span> : "—") },
               { title: "Fournisseur", dataIndex: "fournisseur", width: 140, render: (v) => v || "—" },
               { title: "Péremption", dataIndex: "date_peremption", width: 110, render: (v) => (v ? new Date(v).toLocaleDateString("fr-FR") : "—") },
             ]} />
    </Card>
  );
}

export default function EchantillonDetail({ user }) {
  const { num } = useParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [data, setData] = useState(null);
  const [rapports, setRapports] = useState([]);
  const [lots, setLots] = useState([]);
  const [etapePaiement, setEtapePaiement] = useState("aucune");
  const [err, setErr] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  // Erratum : section concernée (modale ouverte) + formulaire du motif
  const [erratumSection, setErratumSection] = useState(null);
  const [formErratum] = Form.useForm();

  const charger = () => Promise.all([
    api.echantillonComplet(num).then(setData).catch((e) => setErr(e.message)),
    api.rapportsHistorique(num).then((d) => setRapports(Array.isArray(d) ? d : [])).catch(() => setRapports([])),
    api.tracabiliteReactifs(num).then((d) => setLots(Array.isArray(d) ? d : [])).catch(() => setLots([])),
    api.parametresFacturation().then((p) => setEtapePaiement(p?.etape_paiement || "aucune")).catch(() => {}),
  ]);

  const lancerErratum = async ({ motif }) => {
    try {
      await api.erratumRapport(erratumSection, num, motif);
      message.success("Dossier rouvert : corrigez, soumettez puis faites valider la fiche.");
      setErratumSection(null);
      formErratum.resetFields();
      await charger();
    } catch (e) { message.error(e.message); }
  };

  useEffect(() => { charger(); }, [num]);

  const changerStatut = async (statut) => {
    setErr(null);
    setEnvoi(true);
    try {
      await api.changerStatut(num, statut);
      message.success(`Statut mis à jour : ${statut}.`);
      await charger();
    } catch (e) { message.error(e.message); }
    finally { setEnvoi(false); }
  };

  if (err && !data) return <ErreurChargement message={err} onReessayer={() => { setErr(null); charger(); }} />;
  if (!data) return <Flex justify="center" style={{ padding: 48 }}><Spin /></Flex>;

  const e = data.echantillon;
  const statutActuel = e.statut || "Reçu";
  const idxActuel = STATUTS.indexOf(statutActuel);
  // Stepper manuel : admin seulement, jamais vers « Validé » / « Rapport émis » ni depuis « Rapport émis »
  const peutStepper = user.role === "admin";
  const responsable = estResponsable(user.role);
  const fmt = (d) => (d ? String(d).slice(0, 16).replace("T", " ") : "—");
  const sections = Array.isArray(data.sections_actives) ? data.sections_actives : [];
  const rapportDispo = ["Validé", "Rapport émis"].includes(statutActuel);

  const MANUELS = ["Reçu", "En cours", "À valider"];
  const modifiable = statutActuel !== "Rapport émis";
  const precedent = modifiable && idxActuel > 0 && MANUELS.includes(STATUTS[idxActuel - 1])
    ? STATUTS[idxActuel - 1] : null;
  const suivant = modifiable && idxActuel < STATUTS.length - 1 && MANUELS.includes(STATUTS[idxActuel + 1])
    ? STATUTS[idxActuel + 1] : null;

  return (
    <>
      <Flex justify="space-between" align="center" className="page-entete">
        <Space size={10} align="center">
          <Typography.Title level={4} className="page-titre mono">{e.num_echantillon}</Typography.Title>
          <StatutTag statut={statutActuel} />
          <DecisionTag decision={e.decision_reception} />
          <PaiementTag statut={e.payement} />
        </Space>
        <Space>
          <BoutonFichier icon={<PrinterOutlined />} url={api.urlEtiquettes(e.num_echantillon)}>
            Imprimer les étiquettes
          </BoutonFichier>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/echantillons")}>Retour à la liste</Button>
        </Space>
      </Flex>
      {(() => {
        // Facturation (tâche 38) : avertissement si le paiement n'est pas soldé ; blocage côté serveur
        // seulement à l'étape exigée par le réglage (par défaut « aucune »)
        const regle = ["Payé", "Exonéré", "Avoir total"].includes(e.payement);
        const nonSolde = ["Non payé", "À payer", "Partiellement payé"].includes(e.payement);
        if (etapePaiement !== "aucune" && !regle && statutActuel !== "Rapport émis") {
          const etape = etapePaiement === "mise_en_analyse" ? "avant la mise en analyse" : "avant la remise du rapport";
          return <Alert type="warning" showIcon style={{ marginBottom: 12 }}
                        title={`Paiement exigé ${etape} : l'action sera refusée tant que l'échantillon n'est ni payé ni exonéré (statut : ${e.payement || "Non concerné"}).`} />;
        }
        if (nonSolde) {
          return <Alert type="warning" showIcon style={{ marginBottom: 12 }}
                        title={`Paiement non soldé (${e.payement}) : le circuit n'est pas bloqué.`} />;
        }
        return null;
      })()}

      {err && <Alert type="error" title={err} showIcon style={{ marginBottom: 12 }} />}

      {/* Cycle de vie */}
      <Card size="small" className="bloc">
        <Steps
          size="small"
          current={idxActuel}
          status={statutActuel === "Rapport émis" ? "finish" : "process"}
          items={STATUTS.map((s) => ({ title: s }))}
        />
        {peutStepper && (precedent || suivant || statutActuel === "Validé") && (
          <Flex gap={8} align="center" wrap className="statut-actions">
            <Typography.Text type="secondary" className="statut-actions-label">Faire évoluer :</Typography.Text>
            {precedent && (
              <Button size="small" icon={<ArrowLeftOutlined />} loading={envoi}
                      onClick={() => changerStatut(precedent)}>
                {precedent}
              </Button>
            )}
            {suivant && (
              <Button size="small" type="primary" loading={envoi} onClick={() => changerStatut(suivant)}>
                {suivant} <ArrowRightOutlined />
              </Button>
            )}
            {statutActuel === "Validé" && (
              <Tag color="green" style={{ marginLeft: "auto" }}>Prêt pour le rapport d'essai</Tag>
            )}
          </Flex>
        )}
      </Card>

      {/* Informations de réception */}
      <Card size="small" title="Réception" className="bloc">
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2, lg: 3 }}
          items={[
            ["Nature", e.nature],
            ["Catégorie", e.categorie],
            ["Espèce animale", e.espece_animale],
            ["N° de lot", e.num_lot],
            ["Fabricant / Propriétaire", e.fabricant],
            ["Organisme préleveur", e.organisme_preleveur],
            ["Réf. fiche prélèvement", e.ref_fiche_prelevement],
            ["Date réception", <span className="mono">{fmt(e.date_reception)}</span>],
            ["Statut", <StatutTag statut={statutActuel} />],
            ["Décision de réception", e.decision_reception
              ? <Space size={6}>{e.decision_reception}<DecisionTag decision={e.decision_reception} /></Space>
              : "Non renseignée"],
            ["T° à réception", e.temperature_reception != null ? `${String(e.temperature_reception).replace(".", ",")} °C` : null],
            ["Non-conformités", NON_CONFORMITES.filter(([n]) => e[n]).map(([, l]) => l).join(", ") || "Aucune"],
            ["Motif / réserve", e.motif_decision],
            ["Observation", e.non_conformite],
          ].map(([label, v]) => ({ key: label, label, children: v || "—" }))}
        />
      </Card>

      {/* Fiches de traitement par section */}
      <Typography.Text type="secondary" className="sous-titre">Sections et traitements</Typography.Text>
      {sections.length === 0 ? (
        <Card size="small">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Cet échantillon n'est routé vers aucune section." />
        </Card>
      ) : (
        <Row gutter={[16, 16]}>
          {sections.map((sec) => {
            const t = data.traitements?.[sec] || {};
            const rapportValide = rapports.find((r) => r.section === sec && r.statut === "valide");
            const peutErratum = responsable && statutActuel === "Rapport émis"
              && rapportValide && !rapportValide.erratum_motif;
            return (
              <Col xs={24} md={12} lg={8} key={sec}>
                <Card size="small" title={<Space size={8}><SectionTag code={sec} />{LIBELLE_SECTION[sec]}</Space>}>
                  {t.existe ? (
                    <Descriptions size="small" column={1} items={[
                      { key: "s", label: "Fiche saisie par", children: t.saisi_par || "—" },
                      { key: "v", label: "Validée par", children: t.valide_par || "en attente" },
                    ]} />
                  ) : (
                    <Typography.Text type="secondary">Aucune fiche de traitement.</Typography.Text>
                  )}
                  <Flex gap={8} align="center" wrap style={{ marginTop: 12 }}>
                    {(t.existe || e.decision_reception !== "Refusé") ? (
                      <Link to={`/traitement/${sec}`}>
                        <Button type="primary" size="small">{t.existe ? "Voir la fiche" : "Créer la fiche"}</Button>
                      </Link>
                    ) : (
                      <Typography.Text type="danger">Refusé à la réception : pas de fiche de traitement</Typography.Text>
                    )}
                    {t.existe && rapportDispo && (rapportValide || responsable) && (
                      // 1re ouverture = émission officielle : l'historique est rechargé ensuite
                      <BoutonFichier size="small" icon={<FilePdfOutlined />}
                                     url={api.urlRapport(sec, e.num_echantillon)} apres={charger}>
                        {rapportValide && !rapportValide.erratum_motif
                          ? `Rapport ${rapportValide.numero}` : "Rapport d'essai PDF"}
                      </BoutonFichier>
                    )}
                    {t.existe && !rapportDispo && (
                      <Typography.Text type="secondary">Rapport disponible après validation</Typography.Text>
                    )}
                    {t.existe && rapportDispo && !rapportValide && !responsable && (
                      <Typography.Text type="secondary">Rapport à émettre par un responsable</Typography.Text>
                    )}
                    {peutErratum && (
                      <Button size="small" icon={<EditOutlined />} onClick={() => setErratumSection(sec)}>
                        Erratum
                      </Button>
                    )}
                  </Flex>
                </Card>
              </Col>
            );
          })}
        </Row>
      )}

      {ROLES_GLOBAUX.includes(user.role) && (
        <div style={{ marginTop: 16 }}><FacturationEchantillon num={num} sections={sections} user={user} onMaj={charger} /></div>
      )}

      {lots.length > 0 && <div style={{ marginTop: 16 }}><LotsUtilises lots={lots} /></div>}

      {rapports.length > 0 && <div style={{ marginTop: 16 }}><HistoriqueRapports rapports={rapports} /></div>}

      <Modal
        title={`Erratum du rapport ${erratumSection || ""}`}
        open={Boolean(erratumSection)}
        okText="Rouvrir le dossier"
        okButtonProps={{ danger: true }}
        cancelText="Annuler"
        onOk={() => formErratum.submit()}
        onCancel={() => { setErratumSection(null); formErratum.resetFields(); }}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">
          Le dossier repasse « En cours ». Après correction, soumission et validation, la nouvelle émission
          créera la version suivante, qui annule et remplace le rapport actuel (celui-ci reste consultable).
        </Typography.Paragraph>
        <Form form={formErratum} layout="vertical" onFinish={lancerErratum}>
          <Form.Item label="Motif" name="motif"
                     rules={[{ required: true, whitespace: true, message: "Le motif de l'erratum est obligatoire" }]}>
            <Input.TextArea rows={3} autoFocus />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
