import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert, App, Button, Card, Checkbox, Col, Collapse, DatePicker, Divider, Form, Input, InputNumber,
  Radio, Row, Select, Space, Spin, Statistic, Typography,
} from "antd";
import { CheckCircleOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { ErreurChargement } from "../components/etats";
import { useAvertissementSortie } from "../components/sortie";
import { api } from "../api/client";
import { SelectCategorie, SelectIdLib, SelectNature, SelectRef } from "../components/selects";
import { DECISIONS, NON_CONFORMITES, PaiementTag, SECTIONS, SectionTag, formatDH } from "../components/ui";

// Champs du bloc Identification AVANT les listes (num + date en tête)
const IDENT_AVANT = [
  ["num_echantillon", "N° Échantillon (vide = auto)", "text"],
  ["date_reception", "Date de réception", "datetime"],
];
// Champs du bloc Identification APRÈS les listes
const IDENT_APRES = [
  ["espece_animale", "Espèce animale", "text"],
  ["num_lot", "N° de lot", "text"],
  ["client_nom", "Nom du Client", "text"],
  ["adresse_client", "Adresse du Client", "text"],
  ["date_prelevement", "Date de prélèvement", "datetime"],
  ["cadre_demande", "Cadre de la demande", "text"],
];

const AUTRES_BLOCS = [
  { titre: "Prélèvements par section", champs: [
    ["nbre_prlvmts_sma", "Nbre prélèvements SMA", "number"],
    ["nbre_prlvmts_scha", "Nbre prélèvements SCHA", "number"],
    ["nbre_prlvmts_ssa", "Nbre prélèvements SSA", "number"],
  ]},
  { titre: "Dépôts et remises", champs: [
    ["date_depot_ba_bacterio", "Date dépôt BA Bactériologie", "datetime"],
    ["date_depot_ba_chimie", "Date dépôt BA Chimie", "datetime"],
    ["date_depot_ba_sa", "Date dépôt BA SA", "datetime"],
    ["date1_remise_rapport", "Date 1 remise rapport", "datetime"],
    ["date2_remise_rapport", "Date 2 remise rapport", "datetime"],
    ["sortie_ma", "Sortie MA", "datetime"],
    ["sortie_ch", "Sortie CH", "datetime"],
    ["sortie_dc", "Sortie Dc", "datetime"],
  ]},
];

const HISTO_PAIEMENT = [
  ["nb_para_ma", "Nb paramètres MA"], ["montant_total_ma", "Montant total MA"],
  ["nb_para_ch", "Nb paramètres CH"], ["montant_total_ch", "Montant total CH"],
  ["nb_para_sa", "Nb paramètres SA"], ["montant_total_sa", "Montant total SA"],
];


const TOUS = [...IDENT_AVANT, ...IDENT_APRES, ...AUTRES_BLOCS.flatMap((b) => b.champs)];
const DATETIME_FIELDS = new Set(TOUS.filter(([, , t]) => t === "datetime").map(([n]) => n));
const NUMBER_FIELDS = new Set(TOUS.filter(([, , t]) => t === "number").map(([n]) => n));
// Format envoyé à l'API, identique à l'ancien champ datetime-local
const FORMAT_API = "YYYY-MM-DDTHH:mm";

const montant = (v) => {
  const n = Number.parseFloat(String(v ?? "").replace(",", "."));
  return Number.isFinite(n) ? n : 0;
};

/** Objet API → valeurs du formulaire (dates en dayjs, section unique). */
function versFormulaire(e) {
  const v = { ...e };
  DATETIME_FIELDS.forEach((f) => { v[f] = e[f] ? dayjs(String(e[f]).slice(0, 16)) : null; });
  v.section = ["sma", "scha", "ssa"].find((k) => e[k] === "Yes") || undefined;
  return v;
}

export default function EchantillonForm({ edition = false }) {
  const { num } = useParams();
  const navigate = useNavigate();
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();
  const original = useRef({});
  const [err, setErr] = useState(null);
  const [chargement, setChargement] = useState(edition);
  const [envoi, setEnvoi] = useState(false);
  const [modifie, setModifie] = useState(false);   // saisie non enregistrée : avertissement avant de quitter
  const { liberer } = useAvertissementSortie(modifie);
  const [errChargement, setErrChargement] = useState(null);
  const [essai, setEssai] = useState(0);   // « Réessayer » relance le chargement de la fiche

  useEffect(() => {
    if (edition && num) {
      setChargement(true);
      setErrChargement(null);
      api.echantillon(num)
        .then((e) => { original.current = e; form.setFieldsValue(versFormulaire(e)); })
        .catch((e) => setErrChargement(e.message))
        .finally(() => setChargement(false));
    }
  }, [edition, num, essai]); // eslint-disable-line react-hooks/exhaustive-deps

  // Valeurs suivies en direct : cascade type → sous-type, paiement
  const typeId = Form.useWatch("type_echantillon", form);
  // Paiement : champs calculés par la facturation (bloc P), affichés depuis l'objet chargé
  const totalPaiement = montant(original.current.total);
  const montantPaye = montant(original.current.montant_paye);
  const resteAPayer = Math.max(totalPaiement - montantPaye, 0);

  // Montant estimé = total des lignes facturables (tâche 35 : prix figés, analyses saisies et ajoutées
  // à la réception). Affichage seulement : les montants de paiement sont calculés par la facturation.
  const [calcul, setCalcul] = useState(null);
  const calculer = async () => {
    try { setCalcul(await api.facturationLignes(num)); }
    catch (e) { message.error(e.message); }
  };

  const submit = async (values) => {
    setErr(null);
    const { section, ...reste } = values;
    const body = { ...original.current, ...reste };
    // Une seule section : celle choisie à « Yes », les deux autres à « No »
    ["sma", "scha", "ssa"].forEach((k) => { body[k] = section === k ? "Yes" : "No"; });
    DATETIME_FIELDS.forEach((f) => { body[f] = body[f] ? dayjs(body[f]).format(FORMAT_API) : null; });
    NUMBER_FIELDS.forEach((f) => { if (body[f] === "" || body[f] === undefined) body[f] = null; });
    ["total", "montant_paye"].forEach((f) => {
      if (body[f] === "" || body[f] === undefined) body[f] = null;
      else if (body[f] != null) body[f] = String(body[f]);
    });
    if (!body.num_echantillon) delete body.num_echantillon;
    setEnvoi(true);
    try {
      if (edition) {
        await api.modifierEchantillon(num, body);
        liberer(); setModifie(false);
        message.success("Échantillon mis à jour");
        navigate("/echantillons");
      } else {
        const cree = await api.creerEchantillon(body);
        liberer(); setModifie(false);
        // Réception enregistrée : proposer l'impression des étiquettes
        modal.confirm({
          title: `Échantillon ${cree.num_echantillon} enregistré`,
          icon: <CheckCircleOutlined style={{ color: "#00875A" }} />,
          content: "Imprimer les étiquettes des prélèvements maintenant ?",
          okText: "Imprimer les étiquettes",
          cancelText: "Retour à la liste",
          onOk: () => {
            api.ouvrirFichier(api.urlEtiquettes(cree.num_echantillon)).catch((err) => message.error(err.message));
            navigate("/echantillons");
          },
          onCancel: () => navigate("/echantillons"),
        });
      }
    } catch (e2) {
      setErr(e2.message);
      setEnvoi(false);
    }
  };

  const champ = ([name, label, type]) => {
    let controle;
    if (type === "datetime") {
      controle = <DatePicker showTime={{ format: "HH:mm" }} format="DD/MM/YYYY HH:mm" style={{ width: "100%" }} />;
    } else if (type === "number") {
      controle = <InputNumber min={0} precision={0} style={{ width: "100%" }} />;
    } else {
      controle = (
        <Input
          disabled={edition && name === "num_echantillon"}
          placeholder={!edition && name === "num_echantillon"
            ? `Auto : ${new Date().getFullYear()}-SECTION-0001` : undefined}
        />
      );
    }
    return (
      <Col xs={24} sm={12} lg={8} key={name}>
        <Form.Item label={label} name={name}>{controle}</Form.Item>
      </Col>
    );
  };

  const titre = (t) => <Divider titlePlacement="start" className="bloc-titre">{t}</Divider>;

  return (
    <>
      <Typography.Title level={4} className="page-titre" style={{ marginBottom: 16 }}>
        {edition ? `Modifier l'échantillon ${num}` : "Réception d'un échantillon"}
      </Typography.Title>
      <ErreurChargement message={errChargement} onReessayer={() => setEssai((n) => n + 1)} />
      {err && <Alert type="error" title={err} showIcon style={{ marginBottom: 12 }} />}

      <Spin spinning={chargement}>
        <Card size="small">
          <Form
            form={form}
            layout="vertical"
            onFinish={submit}
            onValuesChange={() => setModifie(true)}
            initialValues={{ payement: "Non concerné", ...(edition ? {} : { decision_reception: "Accepté" }) }}
            scrollToFirstError
            className="form-dense"
          >
            {/* Identification : n° + date, puis nature / catégorie, puis le reste */}
            {titre("Identification")}
            <Row gutter={16}>
              {IDENT_AVANT.map(champ)}
              <Col xs={24} sm={12} lg={8}>
                <Form.Item label="Nature de l'échantillon" name="nature"><SelectNature /></Form.Item>
              </Col>
              <Col xs={24} sm={12} lg={8}>
                <Form.Item label="Catégorie de l'échantillon" name="categorie"><SelectCategorie /></Form.Item>
              </Col>
              <Col xs={24} sm={12} lg={8}>
                <Form.Item label="Fabricant ou propriétaire" name="fabricant">
                  <SelectRef charger={api.fabricantsRef} placeholder="Rechercher un fabricant…" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} lg={8}>
                <Form.Item label="Organisme préleveur" name="organisme_preleveur">
                  <SelectRef charger={api.organismesRef} placeholder="Rechercher un organisme…" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} lg={8}>
                <Form.Item label="Type d'échantillon" name="type_echantillon">
                  <SelectIdLib
                    charger={api.typesEchantillonRef}
                    placeholder="Choisir un type…"
                    // Changer de type réinitialise le sous-type (la liste devient celle du nouveau type)
                    onChange={(id) => form.setFieldsValue({ type_echantillon: id, stype_echantillon: null })}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} lg={8}>
                <Form.Item label="Sous-type d'échantillon" name="stype_echantillon">
                  <SelectIdLib
                    dep={typeId}
                    disabled={!typeId}
                    charger={() => (typeId ? api.sousTypesEchantillonRef(typeId) : Promise.resolve([]))}
                    placeholder={typeId ? "Choisir un sous-type…" : "Choisir d'abord un type…"}
                  />
                </Form.Item>
              </Col>
              {IDENT_APRES.map(champ)}
            </Row>

            {AUTRES_BLOCS.map((bloc) => (
              <div key={bloc.titre}>
                {titre(bloc.titre)}
                <Row gutter={16}>{bloc.champs.map(champ)}</Row>
              </div>
            ))}

            {titre("Paiement des analyses")}
            <Alert type="info" showIcon style={{ marginBottom: 12 }}
                   title="Le paiement est géré par la facturation de l'échantillon (lignes, bulletins, encaissements, exonérations), depuis sa fiche détail. Les montants ci-dessous sont calculés." />
            <Row gutter={16} className="paiement-resume" align="middle">
              <Col xs={12} sm={6}>
                <Typography.Text type="secondary">Statut</Typography.Text>
                <div style={{ marginTop: 4 }}>
                  {original.current.payement && original.current.payement !== "Non concerné"
                    ? <PaiementTag statut={original.current.payement} /> : "Non concerné"}
                </div>
              </Col>
              <Col xs={12} sm={6}><Statistic title="Montant dû" value={formatDH(totalPaiement)} /></Col>
              <Col xs={12} sm={6}><Statistic title="Payé" value={formatDH(montantPaye)} /></Col>
              <Col xs={12} sm={6}>
                <Statistic title="Reste dû" value={formatDH(resteAPayer)}
                           styles={{ content: { color: resteAPayer > 0 ? "#9A6700" : "#006644" } }} />
              </Col>
            </Row>
            {edition && (
              <Space style={{ marginTop: 8 }} wrap>
                <Button onClick={calculer} title="Total des lignes facturables de l'échantillon">Montant estimé</Button>
                {calcul && <Typography.Text>Lignes facturables : <b>{formatDH(calcul.total)}</b></Typography.Text>}
                {calcul?.sans_prix?.length > 0 && (
                  <Typography.Text type="warning">Prix à renseigner : {calcul.sans_prix.join(", ")}</Typography.Text>
                )}
              </Space>
            )}
            {original.current.num_quittance && (
              <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
                Dernier encaissement : quittance {original.current.num_quittance}
                {original.current.mode_paiement ? ` (${original.current.mode_paiement})` : ""}
                {original.current.date_quittance ? ` du ${original.current.date_quittance}` : ""}.
              </Typography.Paragraph>
            )}
            <Collapse
              size="small"
              ghost
              items={[{
                key: "histo",
                label: "Détail historique par section",
                forceRender: true,
                children: (
                  <Row gutter={16}>
                    {HISTO_PAIEMENT.map(([n, l]) => (
                      <Col xs={24} sm={12} lg={8} key={n}>
                        <Form.Item label={l} name={n}><Input /></Form.Item>
                      </Col>
                    ))}
                  </Row>
                ),
              }]}
            />

            {titre("Section")}
            <Form.Item name="section" rules={[{ required: true, message: "Choisissez la section de l'échantillon" }]}>
              <Radio.Group>
                {SECTIONS.map((s) => (
                  <Radio key={s.code} value={s.code.toLowerCase()}>
                    <Space size={6}><SectionTag code={s.code} />{s.nom}</Space>
                  </Radio>
                ))}
              </Radio.Group>
            </Form.Item>

            {titre("Non-conformité à la réception")}
            <Row gutter={16}>
              <Col xs={24} sm={12} lg={8}>
                <Form.Item label="Température à réception" name="temperature_reception">
                  <InputNumber step={0.1} precision={1} suffix="°C" style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col xs={24} lg={16}>
                <Form.Item label="Non-conformités constatées">
                  <Space wrap size={[16, 4]}>
                    {NON_CONFORMITES.map(([nom, lib]) => (
                      <Form.Item key={nom} name={nom} valuePropName="checked" noStyle>
                        <Checkbox>{lib}</Checkbox>
                      </Form.Item>
                    ))}
                  </Space>
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} lg={8}>
                <Form.Item label="Décision" name="decision_reception">
                  <Radio.Group optionType="button" buttonStyle="solid"
                               options={DECISIONS.map((d) => ({ value: d, label: d }))} />
                </Form.Item>
              </Col>
              <Col xs={24} lg={16}>
                <Form.Item noStyle dependencies={["decision_reception"]}>
                  {({ getFieldValue }) => {
                    const decision = getFieldValue("decision_reception");
                    const requis = decision === "Refusé" || decision === "Accepté sous réserve";
                    return (
                      <Form.Item label={decision === "Refusé" ? "Motif du refus" : "Motif / réserve"}
                                 name="motif_decision"
                                 rules={requis ? [{ required: true, whitespace: true,
                                   message: `Motif obligatoire pour « ${decision} »` }] : []}>
                        <Input placeholder={requis ? "" : "Facultatif"} />
                      </Form.Item>
                    );
                  }}
                </Form.Item>
              </Col>
            </Row>
            <Form.Item label="Observation" name="non_conformite">
              <Input.TextArea rows={2} />
            </Form.Item>

            <Space>
              <Button type="primary" htmlType="submit" loading={envoi}>
                {edition ? "Mettre à jour" : "Enregistrer"}
              </Button>
              <Button onClick={() => navigate("/echantillons")}>Annuler</Button>
            </Space>
          </Form>
        </Card>
      </Spin>
    </>
  );
}
