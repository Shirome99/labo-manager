import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button, Layout, Menu, Space } from "antd";
import {
  ExperimentOutlined, FileSearchOutlined, HomeOutlined, InboxOutlined, KeyOutlined, LogoutOutlined,
  ProfileOutlined, TableOutlined, TeamOutlined, DatabaseOutlined, AuditOutlined, ToolOutlined, LineChartOutlined, SafetyCertificateOutlined, BarChartOutlined, FileDoneOutlined, ExperimentFilled, WalletOutlined,
} from "@ant-design/icons";
import { api } from "../api/client";
import MotDePasse from "./MotDePasse";
import RechercheGlobale from "./RechercheGlobale";
import Notifications from "./Notifications";
import { ROLES_GLOBAUX, SECTIONS, SectionTag } from "./ui";

const { Header, Sider, Content } = Layout;

// Compteurs du menu : au-delà de 9 999, notation compacte (« 10,9 k ») pour ne pas chevaucher la flèche
const compact = new Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 });
const compteur = (n) => (n != null
  ? <span className="menu-count" title={Number(n).toLocaleString("fr-FR")}>{n >= 10000 ? compact.format(n) : n}</span>
  : null);
const ENVIRONNEMENTS = { production: "Production", test: "Test", developpement: "Développement", local: "Local",
  demo: "Démonstration" };
// Démonstration en ligne (GitHub Pages) : bandeau fixé au build
const DEMO = import.meta.env.VITE_ENVIRONNEMENT === "demo";
const libelle = (to, texte, n) => (
  <Link to={to} className="menu-lien">{texte}{compteur(n)}</Link>
);

export default function Shell({ user, stats = {}, children, onLogout }) {
  const navigate = useNavigate();
  const location = useLocation();
  const role = user?.role;
  const isAdmin = role === "admin";
  const isGlobal = ROLES_GLOBAUX.includes(role);

  // Un rôle sectionnel ne voit que sa propre section
  const voitSection = (code) => isGlobal || role === code.toLowerCase();
  const sectionsVisibles = SECTIONS.filter((s) => voitSection(s.code));

  // Sous-menus de section dépliés par défaut
  const [ouverts, setOuverts] = useState(() => sectionsVisibles.map((s) => s.code));
  const [motDePasse, setMotDePasse] = useState(false);
  const [version, setVersion] = useState(null);
  useEffect(() => { api.version().then(setVersion).catch(() => setVersion(null)); }, []);

  const deconnexion = async () => {
    try { await api.logout(); } catch (e) { /* on déconnecte quand même */ }
    onLogout?.();
    navigate("/login");
  };

  const items = useMemo(() => {
    const general = {
      type: "group", key: "g-general", label: "Général",
      children: [
        { key: "/", icon: <HomeOutlined />, label: libelle("/", "Accueil") },
        { key: "/travail", icon: <InboxOutlined />, label: libelle("/travail", "Mon travail") },
        { key: "/echantillons", icon: <ExperimentOutlined />, label: libelle("/echantillons", "Échantillons", stats.total) },
      ],
    };
    const sections = {
      type: "group", key: "g-sections", label: "Sections",
      children: sectionsVisibles.map((s) => ({
        key: s.code,
        label: (
          <span className="menu-section">
            <SectionTag code={s.code} />
            <span>{s.nom}</span>
            {compteur(stats[s.key])}
          </span>
        ),
        children: [
          { key: `/echantillons?section=${s.code}`, icon: <TableOutlined />,
            label: libelle(`/echantillons?section=${s.code}`, "Échantillons") },
          { key: `/traitement/${s.code}`, icon: <ProfileOutlined />,
            label: libelle(`/traitement/${s.code}`, "Traitement") },
          { key: `/resultats/${s.code}`, icon: <FileSearchOutlined />,
            label: libelle(`/resultats/${s.code}`, "Résultats") },
        ],
      })),
    };
    // Qualité (ISO 17025) : visible par tous, écriture selon le rôle (contrôlée par le serveur)
    const qualite = {
      type: "group", key: "g-qualite", label: "Qualité",
      children: [
        { key: "/equipements", icon: <ToolOutlined />, label: libelle("/equipements", "Équipements") },
        { key: "/controles-qualite", icon: <LineChartOutlined />, label: libelle("/controles-qualite", "Contrôles qualité") },
        { key: "/habilitations", icon: <SafetyCertificateOutlined />, label: libelle("/habilitations", "Habilitations") },
        { key: "/reactifs", icon: <ExperimentFilled />, label: libelle("/reactifs", "Réactifs et milieux") },
      ],
    };
    // Reporting : requêtes et bilans (données limitées à sa section pour un rôle sectionnel, côté serveur)
    const reporting = {
      type: "group", key: "g-reporting", label: "Reporting",
      children: [
        { key: "/requetes", icon: <BarChartOutlined />, label: libelle("/requetes", "Requêtes") },
        { key: "/bilan-mensuel", icon: <FileDoneOutlined />, label: libelle("/bilan-mensuel", "Bilan mensuel") },
      ],
    };
    // Facturation (bloc P) : accueil, responsables, admin ; les rôles de section n'y ont pas accès
    const facturation = {
      type: "group", key: "g-facturation", label: "Facturation",
      children: [
        { key: "/facturation", icon: <WalletOutlined />, label: libelle("/facturation", "Bulletins et caisse") },
      ],
    };
    const admin = {
      type: "group", key: "g-admin", label: "Administration",
      children: [
        { key: "/admin/users", icon: <TeamOutlined />, label: libelle("/admin/users", "Comptes") },
        { key: "/admin/referentiels", icon: <DatabaseOutlined />, label: libelle("/admin/referentiels", "Référentiels") },
        { key: "/admin/audit", icon: <AuditOutlined />, label: libelle("/admin/audit", "Journal d'audit") },
      ],
    };
    const groupes = [general, sections, qualite, reporting];
    if (isGlobal) groupes.push(facturation);
    if (isAdmin) groupes.push(admin);
    return groupes;
  }, [stats, isAdmin, role]); // eslint-disable-line react-hooks/exhaustive-deps

  // Entrée active : la liste filtrée par section a sa propre entrée
  const section = new URLSearchParams(location.search).get("section");
  const cleActive = location.pathname === "/echantillons" && section
    ? `/echantillons?section=${section}`
    : location.pathname;

  return (
    <Layout className="shell">
      <Header className="shell-header">
        <Link to="/" className="brand">Labo Manager</Link>
        <Space size={12} className="shell-header-droite">
          <RechercheGlobale />
          <Notifications />
          <SectionTag code={role} />
          <span className="username">{user?.username}</span>
          <Button size="small" ghost icon={<KeyOutlined />} onClick={() => setMotDePasse(true)}>
            Mot de passe
          </Button>
          <Button size="small" ghost icon={<LogoutOutlined />} onClick={deconnexion}>
            Déconnexion
          </Button>
        </Space>
        <MotDePasse ouvert={motDePasse} onFermer={() => setMotDePasse(false)} />
      </Header>

      <Layout>
        <Sider width={248} className="shell-sider" theme="light"
               style={{ position: "sticky", top: 52, height: "calc(100vh - 52px)", overflowY: "auto" }}>
          <Menu
            mode="inline"
            items={items}
            selectedKeys={[cleActive]}
            openKeys={ouverts}
            onOpenChange={setOuverts}
          />
          {version && (
            <div className="shell-version">
              Labo Manager {version.version} · {ENVIRONNEMENTS[version.environnement] || version.environnement}
            </div>
          )}
        </Sider>
        <Content className="shell-content">
          {(DEMO || version?.environnement === "demo") && (
            <div className="bandeau-test" role="status">Démonstration — données fictives</div>
          )}
          {version?.environnement === "test" && (
            <div className="bandeau-test" role="status">Environnement de test : les données ne sont pas celles du laboratoire.</div>
          )}
          <div className="main-body">{children}</div>
        </Content>
      </Layout>
    </Layout>
  );
}
