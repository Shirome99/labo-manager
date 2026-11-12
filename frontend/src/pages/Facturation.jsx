import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Button, Card, Col, DatePicker, Flex, Input, Row, Select, Space, Statistic, Table, Tabs, Tag, Typography,
} from "antd";
import { DownloadOutlined, FileExcelOutlined, FilePdfOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { api } from "../api/client";
import BoutonFichier from "../components/BoutonFichier";
import BulletinDrawer, { FactureTag } from "../components/BulletinDrawer";
import { ErreurChargement, Vide } from "../components/etats";
import { PaiementTag, formatDH } from "../components/ui";

const arr = (d) => (Array.isArray(d) ? d : []);
const fmtDate = (d) => (d ? dayjs(d).format("DD/MM/YYYY") : "—");
const mono = (v) => <span className="mono">{formatDH(v)}</span>;
const STATUTS_PAIEMENT = ["Non payé", "Partiellement payé", "Payé", "Exonéré", "Avoir total"];

/**
 * Facturation (tâche 39) : bulletins (filtres, recherche par n°), impayés par client et ancienneté,
 * journal de caisse (encaissements d'une période, totaux par mode, exports Excel / PDF signé).
 * ?bulletin=<id> ouvre directement un bulletin (lien des notifications).
 */
export default function Facturation({ user }) {
  const [params, setParams] = useSearchParams();
  const [onglet, setOnglet] = useState(params.get("onglet") || "bulletins");
  const bulletin = params.get("bulletin") ? Number(params.get("bulletin")) : null;
  const [version, setVersion] = useState(0);          // recharge les onglets après une action dans le tiroir

  const ouvrir = (id) => setParams((p) => { const n = new URLSearchParams(p); n.set("bulletin", id); return n; });
  const fermer = () => setParams((p) => { const n = new URLSearchParams(p); n.delete("bulletin"); return n; });

  return (
    <>
      <div className="page-entete">
        <Typography.Title level={4} className="page-titre">Facturation</Typography.Title>
        <Typography.Text type="secondary">Bulletins, impayés et journal de caisse.</Typography.Text>
      </div>
      <Tabs activeKey={onglet} onChange={setOnglet} destroyOnHidden items={[
        { key: "bulletins", label: "Bulletins", children: <Bulletins onOuvrir={ouvrir} version={version} /> },
        { key: "impayes", label: "Impayés", children: <Impayes onOuvrir={ouvrir} version={version} /> },
        { key: "caisse", label: "Journal de caisse", children: <Caisse onOuvrir={ouvrir} version={version} /> },
      ]} />
      <BulletinDrawer id={bulletin} user={user} onFermer={() => { fermer(); setVersion((v) => v + 1); }}
                      onChange={() => setVersion((v) => v + 1)} />
    </>
  );
}

function Bulletins({ onOuvrir, version }) {
  const [filtres, setFiltres] = useState({ type: "facture" });
  const [page, setPage] = useState({ page: 1, taille: 50 });
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [chargement, setChargement] = useState(false);

  const changer = (k, v) => { setFiltres((f) => ({ ...f, [k]: v || undefined })); setPage((p) => ({ ...p, page: 1 })); };

  useEffect(() => {
    setChargement(true);
    const minuteur = setTimeout(() => {
      api.factures({ ...filtres, page: page.page, taille: page.taille })
        .then(setData).catch((e) => setErr(e.message)).finally(() => setChargement(false));
    }, filtres.q || filtres.client ? 300 : 0);
    return () => clearTimeout(minuteur);
  }, [filtres, page, version]);

  const colonnes = [
    {
      title: "N°", dataIndex: "numero", width: 150,
      render: (v, f) => <Button type="link" size="small" className="btn-lien mono" onClick={() => onOuvrir(f.id)}>{v || "Brouillon"}</Button>,
    },
    { title: "Date", key: "date", width: 100, render: (_, f) => fmtDate(f.date_emission || f.cree_le) },
    { title: "Client", dataIndex: "client_nom", ellipsis: true, render: (v) => v || "—" },
    { title: "Échantillons", dataIndex: "echantillons", ellipsis: true, render: (v) => <span className="mono">{v || "—"}</span> },
    { title: "Bulletin", key: "statut", width: 130, render: (_, f) => <FactureTag f={f} /> },
    { title: "Paiement", dataIndex: "statut_paiement", width: 150, render: (v) => <PaiementTag statut={v} /> },
    { title: "Montant", dataIndex: "total_ttc", width: 120, align: "right", render: mono },
    { title: "Reste dû", dataIndex: "reste", width: 120, align: "right", render: (v, f) => (f.type === "facture" && f.statut === "émis" ? mono(v) : "—") },
  ];

  return (
    <>
      <ErreurChargement message={err} onReessayer={() => { setErr(null); setPage((p) => ({ ...p })); }} />
      <Flex gap={8} wrap style={{ marginBottom: 12 }}>
        <Input.Search allowClear placeholder="N° de bulletin ou d'échantillon" style={{ width: 240 }}
                      onChange={(e) => changer("q", e.target.value.trim())} />
        <Input allowClear placeholder="Client" style={{ width: 200 }} onChange={(e) => changer("client", e.target.value.trim())} />
        <DatePicker.RangePicker format="DD/MM/YYYY" onChange={(v) => {
          setFiltres((f) => ({ ...f, du: v?.[0]?.format("YYYY-MM-DD"), au: v?.[1]?.format("YYYY-MM-DD") }));
          setPage((p) => ({ ...p, page: 1 }));
        }} />
        <Select allowClear placeholder="Section" style={{ width: 110 }} onChange={(v) => changer("section", v)}
                options={["SMA", "SCHA", "SSA"].map((s) => ({ value: s, label: s }))} />
        <Select value={filtres.type} style={{ width: 130 }} onChange={(v) => changer("type", v)} allowClear placeholder="Type"
                options={[{ value: "facture", label: "Bulletins" }, { value: "avoir", label: "Avoirs" }]} />
        <Select allowClear placeholder="Statut" style={{ width: 130 }} onChange={(v) => changer("statut", v)}
                options={[{ value: "brouillon", label: "Brouillon" }, { value: "émis", label: "Émis" }, { value: "annulé", label: "Annulé" }]} />
        <Select allowClear placeholder="Paiement" style={{ width: 170 }} onChange={(v) => changer("paiement", v)}
                options={STATUTS_PAIEMENT.map((s) => ({ value: s, label: s }))} />
      </Flex>
      <Table size="small" rowKey="id" columns={colonnes} dataSource={arr(data?.lignes)} loading={chargement}
             locale={{ emptyText: <Vide texte="Aucun bulletin pour ces filtres." /> }}
             pagination={{ current: page.page, pageSize: page.taille, total: data?.total || 0, showSizeChanger: true,
                           showTotal: (n) => `${n} bulletin(s) — reste dû ${formatDH(data?.reste_total ?? 0)}` }}
             onChange={(p) => setPage({ page: p.current, taille: p.pageSize })} />
    </>
  );
}

function Impayes({ onOuvrir, version }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [client, setClient] = useState(null);

  const charger = () => api.impayes().then(setData).catch((e) => setErr(e.message));
  useEffect(() => { charger(); }, [version]); // eslint-disable-line react-hooks/exhaustive-deps

  const tranches = arr(data?.tranches);
  const colonnes = [
    {
      title: "Client", dataIndex: "client",
      render: (v) => <Button type="link" size="small" className="btn-lien" onClick={() => setClient(v === client ? null : v)}>{v}</Button>,
    },
    { title: "Bulletins", dataIndex: "nb", width: 90, align: "right" },
    ...tranches.map((t) => ({ title: `${t} j`, dataIndex: t, width: 120, align: "right", render: (v) => (Number(v) ? mono(v) : "—") })),
    { title: "Reste dû", dataIndex: "total", width: 130, align: "right", render: (v) => <b>{mono(v)}</b> },
  ];
  const bulletins = arr(data?.bulletins).filter((b) => !client || (b.client_nom || "Client non renseigné") === client);

  return (
    <>
      <ErreurChargement message={err} onReessayer={() => { setErr(null); charger(); }} />
      <Row gutter={12} style={{ marginBottom: 12 }}>
        {tranches.map((t) => (
          <Col key={t} xs={12} md={5}><Card size="small"><Statistic title={`${t} jours`} value={formatDH(data?.totaux?.[t])} /></Card></Col>
        ))}
        <Col xs={24} md={4}><Card size="small"><Statistic title="Total des impayés" value={formatDH(data?.totaux?.total)} /></Card></Col>
      </Row>
      <Table size="small" rowKey="client" columns={colonnes} dataSource={arr(data?.clients)} loading={!data && !err}
             pagination={{ pageSize: 50, hideOnSinglePage: true }}
             rowClassName={(r) => (r.client === client ? "ligne-edition" : "")}
             locale={{ emptyText: <Vide texte="Aucun impayé." /> }}
             summary={() => data && arr(data.clients).length > 0 && (
               <Table.Summary.Row>
                 <Table.Summary.Cell index={0}><b>Total</b></Table.Summary.Cell>
                 <Table.Summary.Cell index={1} align="right">{arr(data.bulletins).length}</Table.Summary.Cell>
                 {tranches.map((t, i) => <Table.Summary.Cell key={t} index={i + 2} align="right">{mono(data.totaux[t])}</Table.Summary.Cell>)}
                 <Table.Summary.Cell index={tranches.length + 2} align="right"><b>{mono(data.totaux.total)}</b></Table.Summary.Cell>
               </Table.Summary.Row>
             )} />
      <Typography.Title level={5} style={{ marginTop: 16 }}>
        Bulletins impayés{client ? ` — ${client}` : ""}
      </Typography.Title>
      <Table size="small" rowKey="id" dataSource={bulletins} pagination={{ pageSize: 50, hideOnSinglePage: true }}
             columns={[
               { title: "N°", dataIndex: "numero", width: 150, render: (v, b) => <Button type="link" size="small" className="btn-lien mono" onClick={() => onOuvrir(b.id)}>{v}</Button> },
               { title: "Émis le", dataIndex: "date_emission", width: 100, render: fmtDate },
               { title: "Ancienneté", dataIndex: "jours", width: 110, align: "right", render: (v, b) => <Tag color={v > 90 ? "red" : v > 30 ? "gold" : "default"}>{v} j</Tag> },
               { title: "Client", dataIndex: "client_nom", render: (v) => v || "—" },
               { title: "Échantillons", dataIndex: "echantillons", render: (v) => <span className="mono">{v}</span> },
               { title: "Net", dataIndex: "net", width: 120, align: "right", render: mono },
               { title: "Payé", dataIndex: "paye", width: 120, align: "right", render: mono },
               { title: "Reste dû", dataIndex: "reste", width: 120, align: "right", render: (v) => <b>{mono(v)}</b> },
             ]} />
    </>
  );
}

function Caisse({ onOuvrir, version }) {
  const [periode, setPeriode] = useState([dayjs(), dayjs()]);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const du = periode[0].format("YYYY-MM-DD");
  const au = periode[1].format("YYYY-MM-DD");

  const charger = () => api.caisse({ du, au }).then(setData).catch((e) => setErr(e.message));
  useEffect(() => { setData(null); charger(); }, [du, au, version]); // eslint-disable-line react-hooks/exhaustive-deps

  const modes = Object.entries(data?.par_mode || {});
  return (
    <>
      <ErreurChargement message={err} onReessayer={() => { setErr(null); charger(); }} />
      <Flex justify="space-between" wrap gap={8} style={{ marginBottom: 12 }}>
        <Space wrap>
          <DatePicker.RangePicker value={periode} format="DD/MM/YYYY" allowClear={false}
                                  onChange={(v) => v && setPeriode(v)}
                                  disabledDate={(d) => d && d.isAfter(dayjs(), "day")} />
          <Button onClick={() => setPeriode([dayjs(), dayjs()])}>Aujourd'hui</Button>
        </Space>
        <Space>
          <BoutonFichier icon={<FileExcelOutlined />} url={api.urlExportCaisse({ du, au, format: "xlsx" })}
                         telecharger nom="journal_caisse.xlsx">Export Excel</BoutonFichier>
          <BoutonFichier icon={<FilePdfOutlined />} url={api.urlExportCaisse({ du, au, format: "pdf" })}>PDF signé</BoutonFichier>
        </Space>
      </Flex>
      <Row gutter={12} style={{ marginBottom: 12 }}>
        {modes.map(([m, v]) => (
          <Col key={m} xs={12} md={5}>
            <Card size="small"><Statistic title={`${m.charAt(0).toUpperCase() + m.slice(1)} (${v.nb})`} value={formatDH(v.montant)} /></Card>
          </Col>
        ))}
        <Col xs={24} md={4}>
          <Card size="small"><Statistic title={`Total (${data?.nb ?? 0})`} value={formatDH(data?.total ?? 0)} /></Card>
        </Col>
      </Row>
      <Table size="small" rowKey="id" dataSource={arr(data?.paiements)} loading={!data && !err}
             pagination={{ pageSize: 100, hideOnSinglePage: true }}
             locale={{ emptyText: <Vide texte="Aucun encaissement sur la période." /> }}
             columns={[
               { title: "Date", dataIndex: "date_paiement", width: 100, render: fmtDate },
               {
                 title: "Quittance", dataIndex: "numero_quittance", width: 150,
                 render: (v, p) => <BoutonFichier type="link" size="small" className="btn-lien mono" icon={<DownloadOutlined />}
                                                  url={api.urlQuittance(p.id)}>{v}</BoutonFichier>,
               },
               { title: "Bulletin", dataIndex: "bulletin", width: 150, render: (v, p) => <Button type="link" size="small" className="btn-lien mono" onClick={() => onOuvrir(p.facture_id)}>{v}</Button> },
               { title: "Client", dataIndex: "client_nom", render: (v) => v || "—" },
               { title: "Mode", dataIndex: "mode", render: (v, p) => [v, p.reference, p.banque].filter(Boolean).join(" — ") },
               { title: "Encaissé par", dataIndex: "encaisse_par", width: 110 },
               { title: "Montant", dataIndex: "montant", width: 120, align: "right", render: mono },
             ]} />
      {arr(data?.annules).length > 0 && (
        <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
          Encaissements annulés, exclus des totaux :{" "}
          {data.annules.map((p) => `${p.numero_quittance} (${formatDH(p.montant)}, ${p.motif_annulation})`).join(" ; ")}.
        </Typography.Paragraph>
      )}
      <Typography.Paragraph type="secondary">
        Voir aussi les <Link to="/facturation?onglet=impayes">impayés</Link>.
      </Typography.Paragraph>
    </>
  );
}
