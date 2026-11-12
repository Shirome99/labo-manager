import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import {
  Alert, App, Button, Card, Col, DatePicker, Flex, Form, Input, InputNumber, Row, Select, Space, Tag, Typography,
} from "antd";
import { CheckOutlined, RollbackOutlined, SaveOutlined, SendOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { ErreurChargement } from "../components/etats";
import { api } from "../api/client";
import { TRAITEMENT_FIELDS } from "../api/traitementFields";
import NavigationFile from "../components/NavigationFile";
import { useAvertissementSortie } from "../components/sortie";
import { SelectEchantillon } from "../components/selects";
import { SectionTag, StatutTag, estResponsable as roleResponsable } from "../components/ui";

const LIBELLES = {
  SMA: "Microbiologie Alimentaire",
  SCHA: "Sécurité Chimie Hygiène Alimentaire",
  SSA: "Santé Animale",
};
const FORMAT_DATE_API = "YYYY-MM-DD";

/** Fiche API → valeurs du formulaire (dates en dayjs). */
function versFormulaire(fields, t) {
  const v = {};
  for (const f of fields) {
    const x = t?.[f.name];
    v[f.name] = f.type === "date" ? (x ? dayjs(String(x).slice(0, 10)) : null) : (x ?? null);
  }
  return v;
}

// Lots utilisés : la fiche stocke les codes séparés par des virgules (« L2026-0001, L2026-0004 »).
// Un lot périmé est proposé désactivé ; le serveur refuse tout lot périmé à la date de l'analyse.
function ChoixLots({ value, onChange, lots, disabled }) {
  const codes = (value || "").split(",").map((c) => c.trim()).filter(Boolean);
  const connus = new Set(lots.map((l) => l.code));
  const options = [
    ...lots.map((l) => ({
      value: l.code, disabled: l.etat === "périmé" && !codes.includes(l.code),
      label: `${l.code} — ${l.produit} (lot ${l.numero_lot}, pér. ${dayjs(l.date_peremption).format("DD/MM/YYYY")})${l.etat === "périmé" ? " — périmé" : ""}`,
    })),
    ...codes.filter((c) => !connus.has(c)).map((c) => ({ value: c, label: c })),
  ];
  return (
    <Select mode="multiple" allowClear disabled={disabled} value={codes} placeholder="Choisir les lots utilisés…"
            showSearch={{ optionFilterProp: "label" }} options={options} maxTagCount="responsive"
            onChange={(v) => onChange?.(v.join(", "))} />
  );
}

export default function Traitement({ user }) {
  const { section } = useParams();
  const fields = TRAITEMENT_FIELDS[section] || [];
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();
  const [modifie, setModifie] = useState(false);   // saisie non enregistrée : avertissement avant de quitter
  const { liberer, confirmerAbandon } = useAvertissementSortie(modifie);

  const [num, setNum] = useState("");
  const [echantillon, setEchantillon] = useState(null);
  const [ficheId, setFicheId] = useState(null);
  const [validePar, setValidePar] = useState(null);
  const [err, setErr] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  // Valeurs initiales + compteur d'ouvertures (remonte le formulaire à chaque fiche ouverte)
  const [init, setInit] = useState({});
  const [ouverture, setOuverture] = useState(0);
  const motif = useRef("");

  // Fiche renvoyée par l'API après une action : formulaire monté, mise à jour directe
  // Équipement hors étalonnage / en panne à la date de l'analyse (tâche 17)
  const [contestable, setContestable] = useState(null);
  const [equipements, setEquipements] = useState([]);
  useEffect(() => {
    api.equipements({ section, actifs: "true" })
      .then((d) => setEquipements(Array.isArray(d) ? d : [])).catch(() => setEquipements([]));
  }, [section]);
  // Lots de réactifs / milieux (tâche 20) : actifs de la section et communs ; les périmés sont signalés
  const [lots, setLots] = useState([]);
  useEffect(() => {
    api.reactifs({ section, actifs: "true" })
      .then((d) => setLots(Array.isArray(d) ? d : [])).catch(() => setLots([]));
  }, [section]);
  const relireContestable = (numero) =>
    api.traitement(section, numero).then((d) => setContestable(d?.contestable || null)).catch(() => {});

  const remplir = (t) => {
    form.setFieldsValue(versFormulaire(fields, t || {}));
    setFicheId(t?.id ?? null);
    setValidePar(t?.valide_par ?? null);
  };

  const [errOuverture, setErrOuverture] = useState(null);
  const ouvrirFiche = async (numero) => {
    setNum(numero);
    setErr(null); setErrOuverture(null); setEchantillon(null);
    try {
      const { echantillon, traitement, contestable: c } = await api.traitement(section, numero.trim());
      setContestable(c || null);
      setInit(versFormulaire(fields, traitement || {}));
      setFicheId(traitement?.id ?? null);
      setValidePar(traitement?.valide_par ?? null);
      setOuverture((n) => n + 1);
      setEchantillon(echantillon);
      setModifie(false);
    } catch (e2) {
      setErrOuverture(e2.message);
    }
  };

  // Ouverture directe d'une fiche : /traitement/SMA?num=... (liens des notifications)
  const [params] = useSearchParams();
  const numParam = params.get("num");
  useEffect(() => { if (numParam) ouvrirFiche(numParam); }, [section, numParam]);
  // Changement de section : on repart d'une page vide
  useEffect(() => { if (!numParam) { setEchantillon(null); setNum(""); setErr(null); } }, [section]);

  const majStatut = (s) => setEchantillon((e) => (e ? { ...e, statut: s } : e));

  // Action du circuit de validation, avec retour par message
  const action = async (fn, succes) => {
    setErr(null);
    setEnvoi(true);
    try { await fn(); message.success(succes); }
    catch (e2) { setErr(e2.message); }
    finally { setEnvoi(false); }
  };

  const enregistrer = () => action(async () => {
    const valeurs = form.getFieldsValue(true);
    const body = { num_echantillon: echantillon.num_echantillon };
    for (const f of fields) {
      let v = valeurs[f.name];
      if (f.type === "date" && v) v = dayjs(v).format(FORMAT_DATE_API);
      if (v === "" || v === undefined) v = null;
      body[f.name] = v;
    }
    const saved = await api.enregistrerTraitement(section, body);
    liberer(); setModifie(false);
    remplir(saved);
    relireContestable(echantillon.num_echantillon);
    // Le backend passe Reçu -> En cours à la 1re saisie
    if (["Reçu", null, undefined].includes(echantillon?.statut)) majStatut("En cours");
  }, "Fiche enregistrée.");

  const soumettre = () => action(async () => {
    await api.soumettreTraitement(section, echantillon.num_echantillon);
    majStatut("À valider");
  }, "Fiche soumise à validation.");

  const valider = () => action(async () => {
    const saved = await api.validerTraitement(section, echantillon.num_echantillon);
    remplir(saved);
    majStatut("Validé");
  }, "Fiche validée.");

  const refuser = () => {
    motif.current = "";
    modal.confirm({
      title: "Renvoyer la fiche à l'analyste",
      icon: <RollbackOutlined />,
      content: (
        <Input.TextArea
          rows={3}
          placeholder="Motif du renvoi (optionnel)"
          onChange={(e) => { motif.current = e.target.value; }}
        />
      ),
      okText: "Renvoyer",
      okButtonProps: { danger: true },
      cancelText: "Annuler",
      onOk: () => action(async () => {
        const saved = await api.refuserTraitement(section, echantillon.num_echantillon, motif.current);
        remplir(saved);
        setValidePar(null);
        majStatut("En cours");
      }, "Fiche renvoyée à l'analyste."),
    });
  };

  const statut = echantillon?.statut;
  const estResponsable = roleResponsable(user?.role);
  const verrouille = ["À valider", "Validé", "Rapport émis"].includes(statut);
  const dejaValidee = ["Validé", "Rapport émis"].includes(statut) || Boolean(validePar);
  const peutSoumettre = ficheId && ["Reçu", "En cours"].includes(statut);
  const peutValider = estResponsable && statut === "À valider";
  const peutRefuser = estResponsable && statut === "À valider";

  const controle = (f) => {
    if (f.name === "equipement_utilise") {
      return (
        <Select allowClear showSearch={{ optionFilterProp: "label" }} placeholder="Choisir un équipement…"
                options={equipements.map((q) => ({
                  value: q.code,
                  label: `${q.code} — ${q.designation}${q.statut_echeance === "échu" ? " (étalonnage échu)" : ""}`,
                }))} />
      );
    }
    if (f.name === "lot_reactif") return <ChoixLots lots={lots} />;
    if (f.type === "textarea") return <Input.TextArea rows={2} />;
    if (f.type === "date") return <DatePicker format="DD/MM/YYYY" style={{ width: "100%" }} />;
    if (f.type === "number") return <InputNumber style={{ width: "100%" }} />;
    return <Input />;
  };

  return (
    <>
      <div className="page-entete">
        <Space size={8} align="center">
          <Typography.Title level={4} className="page-titre">Traitement</Typography.Title>
          <SectionTag code={section} />
        </Space>
        <div><Typography.Text type="secondary">{LIBELLES[section]}</Typography.Text></div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Flex gap={12} align="center" wrap>
          <div style={{ flex: "1 1 360px", maxWidth: 560 }}>
            <SelectEchantillon key={section} section={section} value={num || undefined} onChoisir={(n) => confirmerAbandon(() => ouvrirFiche(n))} />
          </div>
          <NavigationFile section={section} num={num} page="traitement" />
        </Flex>
      </div>

      <ErreurChargement message={errOuverture} onReessayer={() => ouvrirFiche(num)} />
      {err && <Alert type="error" title={err} showIcon closable onClose={() => setErr(null)} style={{ marginBottom: 12 }} />}
      {echantillon && contestable && (
        <Alert type="error" showIcon style={{ marginBottom: 12 }}
               title={`Fiche contestable : équipement ${contestable.code} (${contestable.designation})`}
               description={`Non utilisable à la date de l'analyse : ${contestable.raison}.`} />
      )}

      {echantillon && (
        <Card
          size="small"
          title={
            <Space size={10} wrap>
              <span className="mono">{echantillon.num_echantillon}</span>
              <Typography.Text type="secondary" style={{ fontWeight: 400 }}>{echantillon.nature}</Typography.Text>
              <StatutTag statut={statut} />
              {dejaValidee && validePar && <Tag color="green">Validée par {validePar}</Tag>}
            </Space>
          }
        >
          {verrouille && (
            <Alert type="info" showIcon style={{ marginBottom: 12 }}
                   title="Fiche verrouillée : elle a été soumise à validation." />
          )}
          <Form key={ouverture} form={form} initialValues={init} layout="vertical" onValuesChange={() => setModifie(true)}
                disabled={verrouille} className="form-dense">
            <Row gutter={16}>
              {fields.map((f) => (
                <Col key={f.name} xs={24} {...(f.type === "textarea" ? {} : { sm: 12, lg: 8 })}>
                  <Form.Item label={f.label} name={f.name}>{controle(f)}</Form.Item>
                </Col>
              ))}
            </Row>
          </Form>

          <Space wrap>
            {!verrouille && (
              <Button type="primary" icon={<SaveOutlined />} loading={envoi} onClick={enregistrer}>
                {ficheId ? "Mettre à jour" : "Enregistrer la fiche"}
              </Button>
            )}
            {peutSoumettre && (
              <Button icon={<SendOutlined />} loading={envoi} onClick={soumettre}>
                Soumettre à validation
              </Button>
            )}
            {peutValider && (
              <Button type="primary" icon={<CheckOutlined />} loading={envoi} onClick={valider}>
                Valider (double regard)
              </Button>
            )}
            {peutRefuser && (
              <Button danger icon={<RollbackOutlined />} disabled={envoi} onClick={refuser}>
                Renvoyer à l'analyste
              </Button>
            )}
          </Space>
        </Card>
      )}
    </>
  );
}
