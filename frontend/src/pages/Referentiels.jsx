import { useEffect, useState } from "react";
import {
  Alert, App, Badge, Button, Card, Col, Collapse, DatePicker, Flex, Form, Input, InputNumber, Modal, Row, Select, Space,
  Switch, Table, Tabs, Tag, Typography,
} from "antd";
import dayjs from "dayjs";
import { ErreurChargement, Vide } from "../components/etats";
import { api } from "../api/client";
import { SectionTag, formatDH } from "../components/ui";

// Ne jamais laisser une réponse inattendue (objet, HTML mal routé...) faire planter
// le rendu : on force toujours un tableau.
const arr = (d) => (Array.isArray(d) ? d : []);
const requis = (message) => [{ required: true, whitespace: true, message }];

export default function Referentiels() {
  return (
    <>
      <div className="page-entete">
        <Typography.Title level={4} className="page-titre">Référentiels</Typography.Title>
        <Typography.Text type="secondary">Listes de référence des formulaires (administrateur).</Typography.Text>
      </div>
      <Tabs
        defaultActiveKey="fabricants"
        destroyOnHidden
        items={[
          { key: "fabricants", label: "Fabricants", children: <Fabricants /> },
          { key: "categories", label: "Catégories", children: <Categories /> },
          { key: "types", label: "Types d'échantillon", children: <Types /> },
          { key: "soustypes", label: "Sous-types", children: <SousTypes /> },
          { key: "tarifs", label: "Tarifs des analyses", children: <Tarifs /> },
          { key: "delais", label: "Délais de traitement", children: <Delais /> },
        ]}
      />
    </>
  );
}

/* ---------- Gestion générique : formulaire ajout / modification + table ---------- */
/**
 * props :
 *   textes     { ajout, modif, ajoute, modifie, confirmer(r), vide }
 *   charger    () => Promise<rows>
 *   creer, modifier(id, body), supprimer(id)
 *   champs     <Form.Item>… (dans des Col)
 *   colonnes   colonnes antd de la table (sans la colonne d'actions)
 *   versForm   (row) => valeurs du formulaire ;  versBody (valeurs) => corps API
 *   initiales  valeurs d'un formulaire vide
 *   dessus     élément affiché entre le formulaire et la table (ex. filtre)
 *   dep        recharge la table quand il change
 */
function CrudRef({ textes, charger, creer, modifier, supprimer, champs, colonnes,
                   versForm = (r) => r, versBody = (v) => v, initiales = {}, dessus = null, dep = null }) {
  const { modal, message } = App.useApp();
  const [form] = Form.useForm();
  const [rows, setRows] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [editId, setEditId] = useState(null);
  const [err, setErr] = useState(null);

  const recharger = () => {
    setChargement(true);
    return charger()
      .then((d) => setRows(arr(d)))
      .catch((e) => setErr(e.message))
      .finally(() => setChargement(false));
  };
  useEffect(() => { recharger(); }, [dep]); // eslint-disable-line react-hooks/exhaustive-deps

  const reset = () => { form.resetFields(); setEditId(null); };

  const soumettre = async (valeurs) => {
    setErr(null);
    try {
      const body = versBody(valeurs);
      if (editId) { await modifier(editId, body); message.success(textes.modifie); }
      else { await creer(body); message.success(textes.ajoute); }
      reset(); recharger();
    } catch (e2) { setErr(e2.message); }
  };

  const editer = (r) => { setEditId(r.id); form.setFieldsValue(versForm(r)); };
  const confirmerSuppression = (r) => modal.confirm({
    title: textes.confirmer(r),
    okText: "Supprimer", okButtonProps: { danger: true }, cancelText: "Annuler",
    onOk: async () => {
      try { await supprimer(r.id); message.success("Élément supprimé."); recharger(); }
      catch (e) { setErr(e.message); }
    },
  });

  const toutesColonnes = [
    ...colonnes,
    {
      title: "", key: "actions", align: "right", width: 170,
      render: (_, r) => (
        <Space size={12}>
          <Button type="link" size="small" className="btn-lien" onClick={() => editer(r)}>Modifier</Button>
          <Button type="link" size="small" danger className="btn-lien" onClick={() => confirmerSuppression(r)}>
            Supprimer
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <ErreurChargement message={err} onReessayer={() => { setErr(null); recharger(); }} />
      <Card size="small" title={editId ? textes.modif : textes.ajout} className="bloc">
        <Form form={form} layout="vertical" onFinish={soumettre} initialValues={initiales} className="form-dense">
          <Row gutter={16}>{champs}</Row>
          <Space>
            <Button type="primary" htmlType="submit">{editId ? "Enregistrer" : "Ajouter"}</Button>
            {editId && <Button onClick={reset}>Annuler</Button>}
          </Space>
        </Form>
      </Card>
      {dessus}
      <Table size="small" rowKey="id" columns={toutesColonnes} dataSource={rows} loading={chargement}
             rowClassName={(r) => (r.id === editId ? "ligne-edition" : "")}
             pagination={{ defaultPageSize: 50, showSizeChanger: true, hideOnSinglePage: true }}
             locale={{ emptyText: textes.vide }} />
    </>
  );
}

const trierPar = (k) => (a, b) => String(a[k] || "").localeCompare(String(b[k] || ""), "fr");
const tiret = (v) => v || "—";

/* ================= FABRICANTS ================= */
function Fabricants() {
  return (
    <CrudRef
      textes={{
        ajout: "Ajouter un fabricant", modif: "Modifier un fabricant",
        ajoute: "Fabricant ajouté.", modifie: "Fabricant modifié.",
        confirmer: (r) => `Supprimer le fabricant « ${r.libelle} » ?`, vide: "Aucun fabricant.",
      }}
      charger={api.refFabricants} creer={api.creerRefFabricant}
      modifier={api.modifierRefFabricant} supprimer={api.supprimerRefFabricant}
      initiales={{ libelle: "", ville: "", telephone: "" }}
      versForm={(r) => ({ libelle: r.libelle, ville: r.ville || "", telephone: r.telephone || "" })}
      versBody={(v) => ({ libelle: v.libelle, ville: v.ville || "", telephone: v.telephone || "" })}
      champs={<>
        <Col xs={24} md={8}><Form.Item label="Nom" name="libelle" rules={requis("Saisissez le nom")}><Input /></Form.Item></Col>
        <Col xs={24} md={8}><Form.Item label="Ville" name="ville"><Input /></Form.Item></Col>
        <Col xs={24} md={8}><Form.Item label="Téléphone" name="telephone"><Input /></Form.Item></Col>
      </>}
      colonnes={[
        { title: "Nom", dataIndex: "libelle", key: "libelle", sorter: trierPar("libelle") },
        { title: "Ville", dataIndex: "ville", key: "ville", sorter: trierPar("ville"), render: tiret },
        { title: "Téléphone", dataIndex: "telephone", key: "telephone", render: tiret },
      ]}
    />
  );
}

/* ================= CATÉGORIES ================= */
const OPTIONS_DOMAINE = [
  { value: "", label: "— (aucun) —" },
  { value: "SMA", label: "SMA · Microbiologie" },
  { value: "SCHA", label: "SCHA · Chimie" },
  { value: "SSA", label: "SSA · Santé animale" },
];

function Categories() {
  return (
    <CrudRef
      textes={{
        ajout: "Ajouter une catégorie", modif: "Modifier une catégorie",
        ajoute: "Catégorie ajoutée.", modifie: "Catégorie modifiée.",
        confirmer: (r) => `Supprimer la catégorie « ${r.libelle} » ?`, vide: "Aucune catégorie.",
      }}
      charger={api.refCategories} creer={api.creerRefCategorie}
      modifier={api.modifierRefCategorie} supprimer={api.supprimerRefCategorie}
      initiales={{ libelle: "", domaine: "" }}
      versForm={(r) => ({ libelle: r.libelle, domaine: r.domaine || "" })}
      versBody={(v) => ({ libelle: v.libelle, domaine: v.domaine || "" })}
      champs={<>
        <Col xs={24} md={12}><Form.Item label="Libellé" name="libelle" rules={requis("Saisissez le libellé")}><Input /></Form.Item></Col>
        <Col xs={24} md={12}><Form.Item label="Domaine" name="domaine"><Select options={OPTIONS_DOMAINE} /></Form.Item></Col>
      </>}
      colonnes={[
        { title: "Libellé", dataIndex: "libelle", key: "libelle", sorter: trierPar("libelle") },
        {
          title: "Domaine", dataIndex: "domaine", key: "domaine", width: 140,
          filters: ["SMA", "SCHA", "SSA"].map((s) => ({ text: s, value: s })),
          onFilter: (v, r) => r.domaine === v,
          render: (v) => (v ? <SectionTag code={v} /> : "—"),
        },
      ]}
    />
  );
}

/* ================= TYPES ================= */
function Types() {
  return (
    <CrudRef
      textes={{
        ajout: "Ajouter un type d'échantillon", modif: "Modifier un type",
        ajoute: "Type ajouté.", modifie: "Type modifié.",
        confirmer: (r) => `Supprimer le type « ${r.libelle} » ?`, vide: "Aucun type.",
      }}
      charger={api.refTypes} creer={api.creerRefType}
      modifier={api.modifierRefType} supprimer={api.supprimerRefType}
      initiales={{ libelle: "" }}
      versForm={(r) => ({ libelle: r.libelle })}
      versBody={(v) => ({ libelle: v.libelle })}
      champs={
        <Col xs={24} md={12}><Form.Item label="Libellé" name="libelle" rules={requis("Saisissez le libellé")}><Input /></Form.Item></Col>
      }
      colonnes={[
        { title: "Libellé", dataIndex: "libelle", key: "libelle", sorter: trierPar("libelle") },
        {
          title: "Sous-types", dataIndex: "nb_soustypes", key: "nb", width: 120, align: "center",
          sorter: (a, b) => (a.nb_soustypes || 0) - (b.nb_soustypes || 0),
          render: (n) => <Badge count={n || 0} showZero color={n ? "#00875A" : "#C9D1D9"} overflowCount={999} />,
        },
      ]}
    />
  );
}

/* ================= SOUS-TYPES (rattachés à un type) ================= */
function SousTypes() {
  const [types, setTypes] = useState([]);
  const [filtre, setFiltre] = useState(null);   // filtre par type_id
  const { message } = App.useApp();

  useEffect(() => {
    api.refTypes().then((d) => setTypes(arr(d))).catch((e) => message.error(e.message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const optionsTypes = types.map((t) => ({ value: t.id, label: t.libelle }));

  return (
    <CrudRef
      textes={{
        ajout: "Ajouter un sous-type", modif: "Modifier un sous-type",
        ajoute: "Sous-type ajouté.", modifie: "Sous-type modifié.",
        confirmer: (r) => `Supprimer le sous-type « ${r.libelle} » ?`, vide: "Aucun sous-type.",
      }}
      dep={filtre}
      charger={() => api.refSousTypes(filtre || undefined)} creer={api.creerRefSousType}
      modifier={api.modifierRefSousType} supprimer={api.supprimerRefSousType}
      initiales={{ libelle: "", type_id: undefined }}
      versForm={(r) => ({ libelle: r.libelle, type_id: r.type_id || undefined })}
      versBody={(v) => ({ libelle: v.libelle, type_id: Number(v.type_id) })}
      champs={<>
        <Col xs={24} md={12}>
          <Form.Item label="Type parent" name="type_id" rules={[{ required: true, message: "Choisissez le type parent." }]}>
            <Select options={optionsTypes} showSearch={{ optionFilterProp: "label" }} placeholder="Choisir un type…" />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item label="Libellé du sous-type" name="libelle" rules={requis("Saisissez le libellé")}><Input /></Form.Item>
        </Col>
      </>}
      dessus={
        <Space style={{ marginBottom: 12 }}>
          <Typography.Text type="secondary">Filtrer par type</Typography.Text>
          <Select value={filtre} onChange={(v) => setFiltre(v ?? null)} allowClear placeholder="Tous les types"
                  options={optionsTypes} showSearch={{ optionFilterProp: "label" }} style={{ width: 260 }} />
        </Space>
      }
      colonnes={[
        { title: "Sous-type", dataIndex: "libelle", key: "libelle", sorter: trierPar("libelle") },
        {
          title: "Type parent", dataIndex: "type_libelle", key: "type", sorter: trierPar("type_libelle"),
          render: (v) => v || <Tag color="orange">Non rattaché</Tag>,
        },
      ]}
    />
  );
}

/* ================= TARIFS DES ANALYSES (facturation) ================= */
// Prix datés : modifier un prix ouvre une nouvelle période (date d'effet) sans
// écraser l'ancienne. Les analyses du catalogue sans prix en vigueur sont signalées.
const OPTIONS_SECTION = ["SMA", "SCHA", "SSA"].map((s) => ({ value: s, label: s }));
const fmtDate = (d) => (d ? dayjs(d).format("DD/MM/YYYY") : "—");

function Tarifs() {
  const { modal, message } = App.useApp();
  const [rows, setRows] = useState([]);
  const [sansPrix, setSansPrix] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [err, setErr] = useState(null);
  const [dateGrille, setDateGrille] = useState(null);
  const [edition, setEdition] = useState(null);       // null = fermé ; {} = nouveau ; ligne = modification
  const [historiques, setHistoriques] = useState({});

  const charger = () => {
    setChargement(true);
    const params = dateGrille ? `?date=${dateGrille.format("YYYY-MM-DD")}` : "";
    return Promise.all([api.refTarifs(params), api.tarifsSansPrix()])
      .then(([t, s]) => { setRows(arr(t)); setSansPrix(arr(s)); setHistoriques({}); })
      .catch((e) => setErr(e.message))
      .finally(() => setChargement(false));
  };
  useEffect(() => { charger(); }, [dateGrille]); // eslint-disable-line react-hooks/exhaustive-deps

  const chargerHistorique = (id) =>
    api.historiqueRefTarif(id)
      .then((h) => setHistoriques((hs) => ({ ...hs, [id]: arr(h) })))
      .catch((e) => setErr(e.message));

  const confirmerSuppression = (r) => modal.confirm({
    title: `Supprimer le tarif de « ${r.nom_analyse} » (${r.section}) ?`,
    content: "Un tarif qui a un historique de prix ne peut pas être supprimé : désactivez-le.",
    okText: "Supprimer", okButtonProps: { danger: true }, cancelText: "Annuler",
    onOk: async () => {
      try { await api.supprimerRefTarif(r.id); message.success("Tarif supprimé."); charger(); }
      catch (e) { setErr(e.message); }
    },
  });

  const colonnes = [
    { title: "Analyse", dataIndex: "nom_analyse", key: "analyse", sorter: trierPar("nom_analyse") },
    {
      title: "Section", dataIndex: "section", key: "section", width: 90,
      filters: OPTIONS_SECTION.map((o) => ({ text: o.label, value: o.value })),
      onFilter: (v, r) => r.section === v, render: (v) => <SectionTag code={v} />,
    },
    {
      title: dateGrille ? `Prix au ${dateGrille.format("DD/MM/YYYY")}` : "Prix en vigueur", dataIndex: "prix",
      key: "prix", width: 140, align: "right", sorter: (a, b) => Number(a.prix ?? -1) - Number(b.prix ?? -1),
      render: (v) => (v === null || v === undefined
        ? <Tag color="red">Prix à renseigner</Tag>
        : <span className="mono">{formatDH(v)}</span>),
    },
    { title: "Depuis", dataIndex: "depuis", key: "depuis", width: 100, render: fmtDate },
    {
      title: "Quantité", dataIndex: "par_prelevement", key: "pp", width: 130,
      render: (v) => (v ? <Tag color="blue">Par prélèvement</Tag> : <Typography.Text type="secondary">1 par analyse</Typography.Text>),
    },
    {
      title: "État", key: "etat", width: 110,
      filters: [{ text: "À valider", value: "a_valider" }, { text: "Inactif", value: "inactif" }],
      onFilter: (v, r) => (v === "a_valider" ? r.a_valider : !r.actif),
      render: (_, r) => (!r.actif ? <Tag>Inactif</Tag> : r.a_valider ? <Tag color="gold">À valider</Tag> : <Tag color="green">Validé</Tag>),
    },
    {
      title: "", key: "actions", align: "right", width: 160,
      render: (_, r) => (
        <Space size={12}>
          <Button type="link" size="small" className="btn-lien" onClick={() => setEdition(r)}>Modifier</Button>
          <Button type="link" size="small" danger className="btn-lien" onClick={() => confirmerSuppression(r)}>
            Supprimer
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <ErreurChargement message={err} onReessayer={() => { setErr(null); charger(); }} />
      <ReglagesFacturation onErreur={setErr} />
      {sansPrix.length > 0 && (
        <Collapse size="small" className="bloc" items={[{
          key: "sp",
          label: <Space size={8}><Tag color="red">{sansPrix.length}</Tag>analyse(s) du catalogue sans prix en vigueur (prix à renseigner)</Space>,
          children: (
            <Table size="small" rowKey="analyse_id" dataSource={sansPrix} pagination={{ pageSize: 20, hideOnSinglePage: true }}
                   columns={[
                     { title: "Analyse", dataIndex: "nom_analyse" },
                     { title: "Section", dataIndex: "section", width: 90, render: (v) => <SectionTag code={v} /> },
                     { title: "Type", dataIndex: "type_analyse", render: tiret },
                     {
                       title: "", key: "a", align: "right", width: 160,
                       render: (_, a) => (
                         <Button type="link" size="small" className="btn-lien"
                                 onClick={() => setEdition({ nom_analyse: a.nom_analyse, section: a.section, nouveau: true })}>
                           Renseigner le prix
                         </Button>
                       ),
                     },
                   ]} />
          ),
        }]} />
      )}
      <Flex justify="space-between" align="center" wrap gap={8} style={{ marginBottom: 8 }}>
        <Space size={8}>
          <Typography.Text type="secondary">Grille au</Typography.Text>
          <DatePicker value={dateGrille} onChange={setDateGrille} format="DD/MM/YYYY" placeholder="Aujourd'hui"
                      disabledDate={(d) => d && d.isAfter(dayjs(), "day")} />
        </Space>
        <Button type="primary" onClick={() => setEdition({ nouveau: true })}>Ajouter un tarif</Button>
      </Flex>
      <Table
        size="small" rowKey="id" columns={colonnes} dataSource={rows} loading={chargement}
        pagination={{ defaultPageSize: 50, showSizeChanger: true, hideOnSinglePage: true }}
        locale={{ emptyText: <Vide texte="Aucun tarif." /> }}
        expandable={{
          onExpand: (ouvert, r) => { if (ouvert && !historiques[r.id]) chargerHistorique(r.id); },
          expandedRowRender: (r) => (
            <Table size="small" rowKey="id" pagination={false} loading={!historiques[r.id]}
                   dataSource={historiques[r.id] || []}
                   columns={[
                     { title: "Prix", dataIndex: "prix", align: "right", width: 130, render: (v) => <span className="mono">{formatDH(v)}</span> },
                     { title: "Du", dataIndex: "date_debut", width: 110, render: fmtDate },
                     { title: "Au", dataIndex: "date_fin", width: 110, render: (v) => (v ? fmtDate(v) : "en vigueur") },
                     { title: "Saisi par", dataIndex: "cree_par", render: tiret },
                   ]} />
          ),
        }}
      />
      {edition && (
        <TarifModal tarif={edition} onFermer={() => setEdition(null)}
                    onEnregistre={() => { setEdition(null); charger(); }} />
      )}
    </>
  );
}

function TarifModal({ tarif, onFermer, onEnregistre }) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [err, setErr] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const nouveau = !tarif.id;

  const enregistrer = async (v) => {
    setErr(null); setEnvoi(true);
    const body = {
      nom_analyse: v.nom_analyse, section: v.section, prix: Number(v.prix),
      actif: v.actif !== false, par_prelevement: !!v.par_prelevement, a_valider: !v.valide,
      date_effet: (v.date_effet || dayjs()).format("YYYY-MM-DD"),
    };
    try {
      if (nouveau) { await api.creerRefTarif(body); message.success("Tarif ajouté."); }
      else {
        const r = await api.modifierRefTarif(tarif.id, body);
        message.success(r?.nouvelle_periode
          ? `Nouveau prix à partir du ${body.date_effet.split("-").reverse().join("/")} ; l'ancien est conservé.`
          : "Tarif modifié.");
      }
      onEnregistre();
    } catch (e) { setErr(e.message); } finally { setEnvoi(false); }
  };

  return (
    <Modal open title={nouveau ? "Ajouter un tarif" : `Modifier le tarif — ${tarif.nom_analyse}`}
           okText="Enregistrer" cancelText="Annuler" onCancel={onFermer} confirmLoading={envoi}
           onOk={() => form.submit()} destroyOnHidden>
      {err && <Alert type="error" showIcon title={err} style={{ marginBottom: 12 }} />}
      <Form form={form} layout="vertical" className="form-dense" onFinish={enregistrer}
            initialValues={{
              nom_analyse: tarif.nom_analyse || "", section: tarif.section,
              prix: tarif.prix !== undefined && tarif.prix !== null ? Number(tarif.prix) : null,
              date_effet: dayjs(), actif: tarif.actif !== false, par_prelevement: !!tarif.par_prelevement,
              valide: nouveau ? true : !tarif.a_valider,
            }}>
        <Row gutter={12}>
          <Col span={16}>
            <Form.Item label="Analyse (nom exact, comme dans les résultats)" name="nom_analyse"
                       rules={requis("Saisissez le nom de l'analyse")}><Input /></Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="Section" name="section" rules={[{ required: true, message: "Choisissez la section" }]}>
              <Select options={OPTIONS_SECTION} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="Prix unitaire (DH)" name="prix" rules={[{ required: true, message: "Saisissez le prix" }]}>
              <InputNumber min={0} max={1000000} step={10} precision={2} decimalSeparator="," style={{ width: "100%" }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="Date d'effet du prix" name="date_effet"
                       extra={nouveau ? null : "Un prix différent ouvre une nouvelle période à cette date."}>
              <DatePicker format="DD/MM/YYYY" allowClear={false} style={{ width: "100%" }}
                          disabledDate={(d) => d && d.isAfter(dayjs(), "day")} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="Par prélèvement" name="par_prelevement" valuePropName="checked"
                       tooltip="Quantité facturée = nombre de prélèvements de la section"><Switch /></Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="Prix validé" name="valide" valuePropName="checked"
                       tooltip="Les prix repris d'Access sont « à valider » jusqu'à confirmation"><Switch /></Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="Actif" name="actif" valuePropName="checked"><Switch /></Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}

function ReglagesFacturation({ onErreur }) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [etapes, setEtapes] = useState([]);

  useEffect(() => {
    api.parametresFacturation()
      .then((p) => {
        setEtapes(arr(p?.etapes));
        form.setFieldsValue({ taux_tva: Number(p.taux_tva), etape_paiement: p.etape_paiement,
                              seuil_impayes_jours: p.seuil_impayes_jours });
      })
      .catch((e) => onErreur(e.message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const enregistrer = async (v) => {
    try { await api.modifierParametresFacturation(v); message.success("Réglages de facturation enregistrés."); }
    catch (e) { onErreur(e.message); }
  };

  return (
    <Card size="small" title="Réglages de facturation" className="bloc">
      <Form form={form} layout="inline" onFinish={enregistrer} className="form-dense">
        <Form.Item label="TVA (%)" name="taux_tva" rules={[{ required: true, message: "Taux requis" }]}>
          <InputNumber min={0} max={100} precision={2} decimalSeparator="," style={{ width: 90 }} />
        </Form.Item>
        <Form.Item label="Paiement exigé" name="etape_paiement" rules={[{ required: true, message: "Choisissez" }]}>
          <Select options={etapes} style={{ width: 300 }} />
        </Form.Item>
        <Form.Item label="Impayé après (jours)" name="seuil_impayes_jours" rules={[{ required: true, message: "Requis" }]}>
          <InputNumber min={1} max={365} precision={0} style={{ width: 80 }} />
        </Form.Item>
        <Form.Item><Button htmlType="submit">Enregistrer</Button></Form.Item>
      </Form>
    </Card>
  );
}

/* ================= DÉLAIS DE TRAITEMENT ================= */
// Au-delà de N jours après réception sans « Rapport émis », l'échantillon
// est signalé en retard sur le tableau de bord.
const LIBELLE_SECTION = { SMA: "Microbiologie Alimentaire", SCHA: "Chimie / Hygiène", SSA: "Santé Animale" };

function Delais() {
  const { message } = App.useApp();
  const [rows, setRows] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [err, setErr] = useState(null);

  const charger = () => {
    setChargement(true);
    return api.refDelais()
      .then((d) => setRows(arr(d)))
      .catch((e) => setErr(e.message))
      .finally(() => setChargement(false));
  };
  useEffect(() => { charger(); }, []);

  const changer = (section, jours) =>
    setRows((rs) => rs.map((r) => (r.section === section ? { ...r, jours } : r)));

  const enregistrer = async (r) => {
    setErr(null);
    try {
      await api.modifierRefDelai(r.section, Number(r.jours));
      message.success(`Délai ${r.section} : ${r.jours} jours.`);
      charger();
    } catch (e) { setErr(e.message); }
  };

  return (
    <>
      <ErreurChargement message={err} onReessayer={() => { setErr(null); charger(); }} />
      <Typography.Paragraph type="secondary">
        Un échantillon reçu depuis plus de N jours et dont le rapport n'est pas émis est signalé
        « en retard » sur le tableau de bord.
      </Typography.Paragraph>
      <Table
        size="small" rowKey="section" pagination={false} loading={chargement} dataSource={rows}
        columns={[
          {
            title: "Section", dataIndex: "section", key: "section",
            render: (s) => <Space size={8}><SectionTag code={s} />{LIBELLE_SECTION[s]}</Space>,
          },
          {
            title: "Délai (jours)", dataIndex: "jours", key: "jours", width: 160,
            render: (v, r) => (
              <InputNumber min={1} max={365} precision={0} value={v} style={{ width: 100 }}
                           onChange={(j) => changer(r.section, j)} />
            ),
          },
          {
            title: "", key: "actions", align: "right", width: 130,
            render: (_, r) => (
              <Button type="link" size="small" className="btn-lien" disabled={!r.jours}
                      onClick={() => enregistrer(r)}>
                Enregistrer
              </Button>
            ),
          },
        ]}
      />
    </>
  );
}
