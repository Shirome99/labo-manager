import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  Alert, App, Badge, Button, Card, Col, DatePicker, Empty, Flex, Form, Input, Row, Select,
  Segmented, Space, Table, Tag, Typography,
} from "antd";
import {
  DownloadOutlined, FileExcelOutlined, FilterOutlined, PlusOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import { ErreurChargement } from "../components/etats";
import { api } from "../api/client";
import BoutonFichier from "../components/BoutonFichier";
import { SelectRef } from "../components/selects";
import {
  DECISIONS, DecisionTag, PaiementTag, SECTIONS, STATUTS, STATUTS_PAIEMENT, SectionTag, StatutTag,
} from "../components/ui";

const FORMAT_API = "YYYY-MM-DD";

export default function Echantillons({ user }) {
  const { modal, message } = App.useApp();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  // Filtres portés par l'URL (liens directs depuis le tableau de bord)
  const section = params.get("section");
  const filtreStatut = params.get("statut");
  const du = params.get("du") || "";
  const au = params.get("au") || "";
  const fabricant = params.get("fabricant") || "";
  const organisme = params.get("organisme") || "";
  const decision = params.get("decision") || "";
  const paiement = params.get("paiement") || "";
  const retard = params.get("retard") === "1";

  // Pagination, tri et compteurs côté serveur (tâche 30) : une page à la fois
  const [donnees, setDonnees] = useState({ lignes: [], total: 0, compteurs: {} });
  const [page, setPage] = useState(1);
  const [taille, setTaille] = useState(50);
  const [tri, setTri] = useState({ cle: "ordre", ordre: "desc" });
  const qUrl = params.get("q") || "";
  const [q, setQ] = useState(qUrl);
  const [avance, setAvance] = useState(Boolean(du || au || fabricant || organisme));
  const [err, setErr] = useState(null);
  const [chargement, setChargement] = useState(true);

  // Filtres serveur de la liste (les compteurs par statut sont calculés par le serveur sans le filtre statut)
  const filtresServeur = { section, q, du, au, fabricant, organisme, decision, paiement, retard: retard ? "true" : "" };

  const charger = (qv = q, p = page, t = taille, tr = tri) => {
    setChargement(true);
    setErr(null);
    api.echantillons({ ...filtresServeur, q: qv, statut: filtreStatut, page: p, taille: t, tri: tr.cle, ordre: tr.ordre })
      .then((d) => setDonnees({ lignes: Array.isArray(d?.lignes) ? d.lignes : [], total: d?.total || 0,
                                compteurs: d?.compteurs || {} }))
      .catch((e) => setErr(e.message))
      .finally(() => setChargement(false));
  };

  // Un changement de filtre ramène à la 1re page
  useEffect(() => { setQ(qUrl); setPage(1); charger(qUrl, 1); },
    [section, du, au, fabricant, organisme, decision, paiement, retard, qUrl, filtreStatut]); // eslint-disable-line react-hooks/exhaustive-deps

  const changerTable = (pagination, _filtres, sorter) => {
    const cle = sorter?.order ? ({ num: "num_echantillon", reception: "date_reception", statut: "statut" }[sorter.columnKey] || "ordre") : "ordre";
    const nouveauTri = { cle, ordre: sorter?.order === "ascend" ? "asc" : "desc" };
    const nouvellePage = nouveauTri.cle !== tri.cle || nouveauTri.ordre !== tri.ordre || pagination.pageSize !== taille ? 1 : pagination.current;
    setTri(nouveauTri); setTaille(pagination.pageSize); setPage(nouvellePage);
    charger(q, nouvellePage, pagination.pageSize, nouveauTri);
  };
  const ordreColonne = (cle) => (tri.cle === cle ? (tri.ordre === "asc" ? "ascend" : "descend") : null);
  // Le formulaire avancé reflète les filtres de l'URL (remonté quand ils changent)
  const valeursAvance = {
    periode: du || au ? [du ? dayjs(du) : null, au ? dayjs(au) : null] : null,
    fabricant, organisme, decision: decision || undefined, paiement: paiement || undefined,
  };

  const majParams = (valeurs) => {
    const p = new URLSearchParams(params);
    Object.entries(valeurs).forEach(([k, v]) => (v ? p.set(k, v) : p.delete(k)));
    setParams(p);
  };
  const appliquerAvance = ({ periode, fabricant: f, organisme: o, decision: d, paiement: pa }) => majParams({
    du: periode?.[0] ? periode[0].format(FORMAT_API) : "",
    au: periode?.[1] ? periode[1].format(FORMAT_API) : "",
    fabricant: (f || "").trim(), organisme: (o || "").trim(), decision: d || "", paiement: pa || "",
  });
  const effacerAvance = () => majParams({ du: "", au: "", fabricant: "", organisme: "", decision: "", paiement: "" });
  const nbAvances = [du, au, fabricant, organisme, decision, paiement].filter(Boolean).length;

  const supprimer = (num) => modal.confirm({
    title: `Supprimer l'échantillon ${num} ?`,
    content: "Les fiches de traitement liées seront supprimées.",
    okText: "Supprimer", okButtonProps: { danger: true }, cancelText: "Annuler",
    onOk: async () => {
      try { await api.supprimerEchantillon(num); message.success(`Échantillon ${num} supprimé`); charger(); }
      catch (e) { message.error(e.message); }
    },
  });

  const peutEditer = ["admin", "user"].includes(user.role);
  const fmt = (d) => (d ? String(d).slice(0, 10) : "—");
  const lienDetail = (num) => `/echantillons/detail/${encodeURIComponent(num)}`;

  const totalTous = Object.values(donnees.compteurs).reduce((a, n) => a + n, 0);
  const exportParams = { ...filtresServeur, statut: filtreStatut };

  const colonnes = [
    {
      title: "N° Échantillon", dataIndex: "num_echantillon", key: "num",
      sorter: true, sortOrder: ordreColonne("num_echantillon"),
      render: (v) => <Link className="mono cell-num" to={lienDetail(v)}>{v}</Link>,
    },
    { title: "Nature", dataIndex: "nature", key: "nature", ellipsis: true, render: (v) => v || "—" },
    {
      title: "Réception", dataIndex: "date_reception", key: "reception", width: 120,
      sorter: true, sortOrder: ordreColonne("date_reception"),
      render: (v) => <span className="mono cell-date">{fmt(v)}</span>,
    },
    {
      title: "Section", key: "sections", width: 110,
      render: (_, r) => (
        <Space size={4}>
          {r.sma === "Yes" && <SectionTag code="SMA" />}
          {r.scha === "Yes" && <SectionTag code="SCHA" />}
          {r.ssa === "Yes" && <SectionTag code="SSA" />}
        </Space>
      ),
    },
    {
      title: "Statut", dataIndex: "statut", key: "statut", width: 200,
      sorter: true, sortOrder: ordreColonne("statut"),
      render: (v, r) => <Space size={4}><StatutTag statut={v} /><DecisionTag decision={r.decision_reception} /></Space>,
    },
    {
      title: "Paiement", key: "paiement", width: 170,
      render: (_, r) => (
        <Space size={4}>
          <PaiementTag statut={r.payement} />
          {r.total ? <span className="mono cell-date">{r.total} MAD</span> : null}
        </Space>
      ),
    },
    {
      title: "", key: "actions", align: "right", width: 200,
      render: (_, r) => (
        <Space size={12}>
          <Link to={lienDetail(r.num_echantillon)}>Détail</Link>
          {peutEditer && <Link to={`/echantillons/modifier/${encodeURIComponent(r.num_echantillon)}`}>Modifier</Link>}
          {peutEditer && (
            <Button type="link" danger size="small" className="btn-lien" onClick={() => supprimer(r.num_echantillon)}>
              Supprimer
            </Button>
          )}
        </Space>
      ),
    },
  ];

  const filtreActif = q || filtreStatut || section || nbAvances || retard;

  return (
    <>
      <Flex justify="space-between" align="flex-start" className="page-entete">
        <div>
          <Typography.Title level={4} className="page-titre">Échantillons</Typography.Title>
          <Space size={6}>
            <Typography.Text type="secondary">
              {chargement ? "Chargement…" : `${donnees.total} échantillon${donnees.total > 1 ? "s" : ""}`}
            </Typography.Text>
            {section && <SectionTag code={section} />}
          </Space>
        </div>
        <Space>
          <BoutonFichier icon={<FileExcelOutlined />} url={api.urlExportEchantillons(exportParams, "xlsx")}
                         telecharger nom="echantillons.xlsx">
            Export Excel
          </BoutonFichier>
          <BoutonFichier icon={<DownloadOutlined />} url={api.urlExportEchantillons(exportParams, "csv")}
                         telecharger nom="echantillons.csv">
            CSV
          </BoutonFichier>
          {peutEditer && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/echantillons/ajouter")}>
              Nouvel échantillon
            </Button>
          )}
        </Space>
      </Flex>

      {/* Recherche + filtres section */}
      <Flex gap={12} wrap align="center" className="liste-barre">
        <Input.Search
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onSearch={(v) => { setPage(1); charger(v, 1); }}
          allowClear
          placeholder="Rechercher un n°, une nature, un fabricant…"
          style={{ width: 380 }}
        />
        <Segmented
          value={section || ""}
          onChange={(v) => majParams({ section: v })}
          options={[{ value: "", label: "Toutes" }, ...SECTIONS.map((s) => ({ value: s.code, label: s.code }))]}
        />
        <Badge count={nbAvances} size="small" color="#00875A">
          <Button icon={<FilterOutlined />} type={avance ? "primary" : "default"} ghost={avance}
                  onClick={() => setAvance(!avance)}>
            Recherche avancée
          </Button>
        </Badge>
        {retard && (
          <Tag color="red" closable onClose={(e) => { e.preventDefault(); majParams({ retard: "" }); }}>
            En retard
          </Tag>
        )}
      </Flex>

      {/* Recherche avancée : période de réception, fabricant, organisme (filtres serveur) */}
      {avance && (
        <Card size="small" className="recherche-avancee">
          <Form key={[du, au, fabricant, organisme].join("|")} layout="vertical"
                initialValues={valeursAvance} onFinish={appliquerAvance}>
            <Row gutter={16}>
              <Col xs={24} md={8}>
                <Form.Item label="Période de réception" name="periode">
                  <DatePicker.RangePicker allowEmpty={[true, true]} format="DD/MM/YYYY"
                                          placeholder={["Du", "Au"]} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Fabricant ou propriétaire" name="fabricant">
                  <SelectRef charger={api.fabricantsRef} placeholder="Tous les fabricants" />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Organisme préleveur" name="organisme">
                  <SelectRef charger={api.organismesRef} placeholder="Tous les organismes" />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Paiement" name="paiement">
                  <Select allowClear placeholder="Tous" options={STATUTS_PAIEMENT.map((p) => ({ value: p, label: p }))} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Décision de réception" name="decision">
                  <Select allowClear placeholder="Toutes" options={DECISIONS.map((d) => ({ value: d, label: d }))} />
                </Form.Item>
              </Col>
            </Row>
            <Space>
              <Button type="primary" htmlType="submit">Appliquer</Button>
              {nbAvances > 0 && <Button type="link" onClick={effacerAvance}>Effacer les filtres</Button>}
            </Space>
          </Form>
        </Card>
      )}

      {/* Filtres par statut (compteurs calculés par le serveur avec les autres filtres) */}
      <Segmented
        className="filtre-statuts"
        value={filtreStatut || ""}
        onChange={(v) => majParams({ statut: v })}
        options={[
          { value: "", label: `Tous les statuts (${totalTous})` },
          ...STATUTS.map((s) => ({ value: s, label: `${s} (${donnees.compteurs[s] || 0})` })),
        ]}
      />

      <ErreurChargement message={err} onReessayer={() => charger()} />

      <Table
        size="small"
        rowKey="ordre"
        columns={colonnes}
        dataSource={donnees.lignes}
        loading={chargement}
        onChange={changerTable}
        pagination={{ current: page, pageSize: taille, total: donnees.total, showSizeChanger: true,
                      pageSizeOptions: [20, 50, 100, 200],
                      showTotal: (t) => `${t} échantillon${t > 1 ? "s" : ""}`, hideOnSinglePage: false }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={filtreActif ? "Aucun résultat pour ces filtres." : "Aucun échantillon enregistré."}
            >
              {peutEditer && !q && !filtreStatut && (
                <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/echantillons/ajouter")}>
                  Nouvel échantillon
                </Button>
              )}
            </Empty>
          ),
        }}
      />
    </>
  );
}
