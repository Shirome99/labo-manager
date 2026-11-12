import { useEffect, useState } from "react";
import {
  Alert, App, AutoComplete, Button, Card, Col, Flex, Form, Input, InputNumber, Modal, Radio, Row, Space, Statistic,
  Table, Tag, Tooltip, Typography,
} from "antd";
import { FileTextOutlined, LockOutlined, PlusOutlined, SyncOutlined } from "@ant-design/icons";
import { api } from "../api/client";
import BulletinDrawer, { FactureTag } from "./BulletinDrawer";
import { ExonerationModal, useDemanderMotif } from "./Encaissements";
import { ErreurChargement } from "./etats";
import { PaiementTag, ROLES_FACTURATION, SectionTag, estResponsable, formatDH } from "./ui";

const arr = (d) => (Array.isArray(d) ? d : []);

/**
 * Bloc « Facturation » d'un échantillon (tâche 35) : lignes facturables (prix figé à la création),
 * totaux par section et total général. Lecture : rôles globaux ; modification : accueil et admin.
 * props : num, sections (sections de l'échantillon), user, onMaj (statut de paiement changé)
 */
export default function FacturationEchantillon({ num, sections, user, onMaj }) {
  const { message, modal } = App.useApp();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const [ajout, setAjout] = useState(null);          // null | "analyse" | "divers"
  const [edition, setEdition] = useState(null);      // ligne en cours de modification
  const [factures, setFactures] = useState([]);
  const [bulletin, setBulletin] = useState(null);    // id du bulletin ouvert dans le tiroir
  const [exonerer, setExonerer] = useState(false);
  const demanderMotif = useDemanderMotif();
  const peutModifier = ROLES_FACTURATION.includes(user.role);

  const charger = () => Promise.all([
    api.facturationLignes(num).then(setData),
    api.facturesEchantillon(num).then((d) => setFactures(arr(d))),
  ]).catch((e) => setErr(e.message));

  const creerBulletin = async () => {
    setEnvoi(true);
    try {
      const f = await api.creerFacture({ echantillons: [num] });
      setBulletin(f.id);
      charger();
    } catch (e) { message.error(e.message); } finally { setEnvoi(false); }
  };
  useEffect(() => { charger(); }, [num]); // eslint-disable-line react-hooks/exhaustive-deps

  const synchroniser = async () => {
    setEnvoi(true);
    try {
      const r = await api.synchroniserFacturation(num);
      setData(r);
      const n = arr(r.ajoutees).length, m = arr(r.retirees).length;
      message.success(n || m ? `Lignes mises à jour : ${n} ajoutée(s), ${m} retirée(s).` : "Les lignes sont déjà à jour.");
    } catch (e) { message.error(e.message); } finally { setEnvoi(false); }
  };

  const supprimer = (l) => modal.confirm({
    title: `Retirer la ligne « ${l.analyse} » ?`,
    okText: "Retirer", okButtonProps: { danger: true }, cancelText: "Annuler",
    onOk: async () => {
      try { setData(await api.supprimerLigneFacturation(l.id)); message.success("Ligne retirée."); }
      catch (e) { message.error(e.message); }
    },
  });

  if (err) return <ErreurChargement message={err} onReessayer={() => { setErr(null); charger(); }} />;

  const lignes = arr(data?.lignes);
  const parSection = Object.entries(data?.par_section || {});

  const colonnes = [
    {
      title: "Section", dataIndex: "section", width: 80,
      render: (v) => (v ? <SectionTag code={v} /> : <Tag>Divers</Tag>),
    },
    {
      title: "Analyse / libellé", dataIndex: "analyse",
      render: (v, l) => (
        <Space size={6}>
          {v}
          {l.origine === "automatique" && (
            <Tooltip title="Proposée à partir des résultats saisis"><Tag className="tag-code">auto</Tag></Tooltip>
          )}
          {l.verrouillee && <Tooltip title="Portée par un bulletin émis"><LockOutlined /></Tooltip>}
        </Space>
      ),
    },
    {
      title: "Qté", dataIndex: "quantite", width: 90, align: "right",
      render: (v, l) => (
        <Tooltip title={l.par_prelevement ? "Facturée par prélèvement" : null}>
          <span className="mono">{Number(v).toLocaleString("fr-FR")}{l.par_prelevement ? " prl." : ""}</span>
        </Tooltip>
      ),
    },
    {
      title: "Prix unitaire", dataIndex: "prix_unitaire", width: 130, align: "right",
      render: (v) => (v === null || v === undefined
        ? <Tag color="red" style={{ marginInlineEnd: 0 }}>Prix à renseigner</Tag>
        : <span className="mono">{formatDH(v)}</span>),
    },
    { title: "Montant", dataIndex: "montant", width: 130, align: "right", render: (v) => <span className="mono">{formatDH(v)}</span> },
  ];
  if (peutModifier) {
    colonnes.push({
      title: "", key: "actions", width: 150, align: "right",
      render: (_, l) => (l.verrouillee ? null : (
        <Space size={12}>
          <Button type="link" size="small" className="btn-lien" onClick={() => setEdition(l)}>Modifier</Button>
          <Button type="link" size="small" danger className="btn-lien" onClick={() => supprimer(l)}>Retirer</Button>
        </Space>
      )),
    });
  }

  return (
    <Card size="small" title="Facturation" className="bloc" loading={!data}
          extra={peutModifier && (
            <Space size={8} wrap>
              <Button size="small" icon={<SyncOutlined />} loading={envoi} onClick={synchroniser}>
                Mettre à jour depuis les analyses
              </Button>
              <Button size="small" icon={<PlusOutlined />} onClick={() => setAjout("analyse")}>Analyse</Button>
              <Button size="small" icon={<PlusOutlined />} onClick={() => setAjout("divers")}>Frais divers</Button>
              <Button size="small" type="primary" icon={<FileTextOutlined />} loading={envoi} onClick={creerBulletin}
                      disabled={!lignes.some((l) => !l.verrouillee) || factures.some((f) => f.statut === "brouillon")}>
                Bulletin
              </Button>
            </Space>
          )}>
      {data?.paiement && (
        <Flex align="center" gap={12} wrap style={{ marginBottom: 8 }}>
          <Typography.Text type="secondary">Paiement :</Typography.Text>
          <PaiementTag statut={data.paiement.statut} />
          {data.paiement.statut === "Non concerné" && <Typography.Text type="secondary">Non concerné</Typography.Text>}
          <Typography.Text>Dû : <b className="mono">{formatDH(data.paiement.du)}</b></Typography.Text>
          <Typography.Text>Payé : <b className="mono">{formatDH(data.paiement.paye)}</b></Typography.Text>
          <Typography.Text>Reste : <b className="mono">{formatDH(data.paiement.reste)}</b></Typography.Text>
          {estResponsable(user.role) && !data.paiement.exoneration && !factures.some((f) => f.type === "facture" && f.statut !== "annulé") && (
            <Button size="small" onClick={() => setExonerer(true)}>Exonérer l'échantillon</Button>
          )}
        </Flex>
      )}
      {data?.paiement?.exoneration && (
        <Alert type="info" showIcon style={{ marginBottom: 8 }}
               title={`Échantillon exonéré (${data.paiement.exoneration.type}) par ${data.paiement.exoneration.accorde_par} : ${data.paiement.exoneration.motif}`}
               action={estResponsable(user.role) && (
                 <Button size="small" onClick={() => demanderMotif("Annuler l'exonération de l'échantillon ?", async (motif) => {
                   try { setData(await api.annulerExoneration(data.paiement.exoneration.id, motif)); message.success("Exonération annulée."); }
                   catch (e) { message.error(e.message); throw e; }
                 })}>Annuler l'exonération</Button>
               )} />
      )}
      {arr(data?.sans_prix).length > 0 && (
        <Alert type="warning" showIcon style={{ marginBottom: 8 }}
               title={`Prix à renseigner (comptés 0) : ${data.sans_prix.join(", ")}`} />
      )}
      <Table size="small" rowKey="id" columns={colonnes} dataSource={lignes} pagination={false}
             locale={{ emptyText: "Aucune ligne : les analyses saisies dans les résultats apparaîtront ici." }} />
      <Row gutter={16} style={{ marginTop: 12 }}>
        {parSection.map(([s, p]) => (
          <Col key={s}>
            <Statistic title={`${s} (${p.nb} ligne${p.nb > 1 ? "s" : ""})`} value={formatDH(p.montant)}
                       styles={{ content: { fontSize: 16 } }} />
          </Col>
        ))}
        <Col>
          <Statistic title="Total" value={formatDH(data?.total ?? 0)} styles={{ content: { fontSize: 16, fontWeight: 600 } }} />
        </Col>
      </Row>
      {factures.length > 0 && (
        <>
          <Typography.Title level={5} style={{ marginTop: 16, marginBottom: 8 }}>Bulletins et avoirs</Typography.Title>
          <Table size="small" rowKey="id" pagination={false} dataSource={factures} columns={[
            {
              title: "N°", dataIndex: "numero",
              render: (v, f) => <Button type="link" size="small" className="btn-lien mono" onClick={() => setBulletin(f.id)}>{v || "Brouillon"}</Button>,
            },
            { title: "Statut", key: "statut", width: 150, render: (_, f) => <FactureTag f={f} /> },
            { title: "Date", dataIndex: "date_emission", width: 110, render: (v) => (v ? new Date(v).toLocaleDateString("fr-FR") : "—") },
            { title: "Montant", dataIndex: "total_ttc", width: 130, align: "right", render: (v) => <span className="mono">{formatDH(v)}</span> },
            { title: "Net", dataIndex: "net", width: 130, align: "right", render: (v, f) => (f.type === "facture" ? <span className="mono">{formatDH(v)}</span> : "—") },
          ]} />
        </>
      )}
      {exonerer && (
        <ExonerationModal titre={`Exonérer l'échantillon ${num}`} envoyer={(v) => api.exonererEchantillon(num, v)}
                          onFermer={() => setExonerer(false)}
                          onFait={(d) => { setExonerer(false); setData(d); onMaj?.(); message.success("Échantillon exonéré."); }} />
      )}
      <BulletinDrawer id={bulletin} user={user} onFermer={() => { setBulletin(null); charger(); onMaj?.(); }} onChange={charger} />
      {ajout && (
        <AjoutLigne num={num} mode={ajout} sections={sections} onFermer={() => setAjout(null)}
                    onFait={(d) => { setData(d); setAjout(null); }} />
      )}
      {edition && (
        <EditionLigne ligne={edition} onFermer={() => setEdition(null)}
                      onFait={(d) => { setData(d); setEdition(null); }} />
      )}
    </Card>
  );
}

function AjoutLigne({ num, mode, sections, onFermer, onFait }) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [grille, setGrille] = useState([]);
  const [err, setErr] = useState(null);
  const section = Form.useWatch("section", form);

  useEffect(() => {
    if (mode === "analyse") api.grilleTarifs().then((g) => setGrille(arr(g))).catch(() => setGrille([]));
  }, [mode]);

  const options = grille
    .filter((t) => t.section === section && t.actif)
    .map((t) => ({ value: t.nom_analyse, label: `${t.nom_analyse} — ${t.prix === null ? "prix à renseigner" : formatDH(t.prix)}` }));

  const enregistrer = async (v) => {
    setErr(null);
    const body = mode === "divers"
      ? { analyse: v.analyse, prix_unitaire: v.prix_unitaire, quantite: v.quantite || 1 }
      : { section: v.section, analyse: v.analyse, ...(v.quantite ? { quantite: v.quantite } : {}) };
    try {
      const r = await api.ajouterLigneFacturation(num, body);
      message.success("Ligne ajoutée.");
      onFait(r);
    } catch (e) { setErr(e.message); }
  };

  return (
    <Modal open title={mode === "divers" ? "Ajouter des frais divers" : "Ajouter une analyse à facturer"}
           okText="Ajouter" cancelText="Annuler" onOk={() => form.submit()} onCancel={onFermer} destroyOnHidden>
      {err && <Alert type="error" showIcon title={err} style={{ marginBottom: 12 }} />}
      <Form form={form} layout="vertical" className="form-dense" onFinish={enregistrer}
            initialValues={{ section: sections[0] }}>
        {mode === "analyse" && (
          <Form.Item label="Section" name="section" rules={[{ required: true, message: "Choisissez la section" }]}>
            <Radio.Group options={sections.map((s) => ({ value: s, label: s }))} optionType="button" />
          </Form.Item>
        )}
        <Form.Item label={mode === "divers" ? "Libellé" : "Analyse"} name="analyse"
                   rules={[{ required: true, whitespace: true, message: "Saisissez le libellé" }]}
                   extra={mode === "analyse" ? "Prix de la grille du jour, figé sur la ligne." : null}>
          {mode === "divers" ? <Input /> : (
            <AutoComplete options={options} showSearch={{ filterOption: (s, o) => o.value.toLowerCase().includes(s.toLowerCase()) }} />
          )}
        </Form.Item>
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item label="Quantité" name="quantite"
                       extra={mode === "analyse" ? "Vide : 1, ou le nombre de prélèvements si le tarif est par prélèvement." : null}>
              <InputNumber min={0.01} max={10000} precision={2} decimalSeparator="," style={{ width: "100%" }} />
            </Form.Item>
          </Col>
          {mode === "divers" && (
            <Col span={12}>
              <Form.Item label="Montant unitaire (DH)" name="prix_unitaire" rules={[{ required: true, message: "Saisissez le montant" }]}>
                <InputNumber min={0} max={1000000} precision={2} decimalSeparator="," style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          )}
        </Row>
      </Form>
    </Modal>
  );
}

function EditionLigne({ ligne, onFermer, onFait }) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [err, setErr] = useState(null);

  const enregistrer = async (v) => {
    setErr(null);
    try {
      const r = await api.modifierLigneFacturation(ligne.id, {
        analyse: v.analyse, quantite: v.quantite, prix_unitaire: v.prix_unitaire ?? null,
      });
      message.success("Ligne modifiée.");
      onFait(r);
    } catch (e) { setErr(e.message); }
  };

  return (
    <Modal open title="Modifier la ligne" okText="Enregistrer" cancelText="Annuler"
           onOk={() => form.submit()} onCancel={onFermer} destroyOnHidden>
      {err && <Alert type="error" showIcon title={err} style={{ marginBottom: 12 }} />}
      <Typography.Paragraph type="secondary">
        Le prix unitaire a été figé à la création de la ligne ; le modifier ici ne change pas la grille.
      </Typography.Paragraph>
      <Form form={form} layout="vertical" className="form-dense" onFinish={enregistrer}
            initialValues={{
              analyse: ligne.analyse, quantite: Number(ligne.quantite),
              prix_unitaire: ligne.prix_unitaire === null ? null : Number(ligne.prix_unitaire),
            }}>
        <Form.Item label="Analyse / libellé" name="analyse" rules={[{ required: true, whitespace: true, message: "Libellé requis" }]}>
          <Input />
        </Form.Item>
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item label="Quantité" name="quantite" rules={[{ required: true, message: "Quantité requise" }]}>
              <InputNumber min={0.01} max={10000} precision={2} decimalSeparator="," style={{ width: "100%" }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="Prix unitaire (DH)" name="prix_unitaire" extra="Vide : prix à renseigner.">
              <InputNumber min={0} max={1000000} precision={2} decimalSeparator="," style={{ width: "100%" }} />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}
