import { useCallback, useEffect, useRef, useState } from "react";
import { createBrowserRouter, Navigate, Route, RouterProvider, Routes, useLocation } from "react-router-dom";
import { api } from "./api/client";
import Shell from "./components/Shell";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Echantillons from "./pages/Echantillons";
import EchantillonForm from "./pages/EchantillonForm";
import EchantillonDetail from "./pages/EchantillonDetail";
import Traitement from "./pages/Traitement";
import Resultats from "./pages/Resultats";
import Admin from "./pages/Admin";
import Referentiels from "./pages/Referentiels";
import Audit from "./pages/Audit";
import Travail from "./pages/Travail";
import Equipements from "./pages/Equipements";
import ControlesQualite from "./pages/ControlesQualite";
import Habilitations from "./pages/Habilitations";
import Reactifs from "./pages/Reactifs";
import Requetes from "./pages/Requetes";
import BilanMensuel from "./pages/BilanMensuel";
import Facturation from "./pages/Facturation";
import PageIntrouvable from "./pages/PageIntrouvable";
import { ROLES_GLOBAUX } from "./components/ui";

// Routeur de données (createBrowserRouter) : nécessaire à useBlocker (avertissement avant de quitter
// un formulaire modifié). Une seule route « * » rend l'application, qui garde ses <Routes> imbriquées.
// basename : sous-dossier du site (GitHub Pages : /<depot>/ ; « / » en local)
const router = createBrowserRouter([{ path: "*", element: <Racine /> }],
  { basename: import.meta.env.BASE_URL.replace(/\/$/, "") || "/" });

export default function App() {
  return (
    <>
      <Reveil />
      <RouterProvider router={router} />
    </>
  );
}

// API gratuite de Render endormie : 1er appel long (jusqu'à une minute), annoncé après 3 s
function Reveil() {
  const [attente, setAttente] = useState(false);
  useEffect(() => {
    const surReveil = (e) => setAttente(e.detail);
    window.addEventListener("lims:reveil", surReveil);
    return () => window.removeEventListener("lims:reveil", surReveil);
  }, []);
  if (!attente) return null;
  return <div className="bandeau-reveil" role="status">Démarrage du serveur, merci de patienter…</div>;
}

function Racine() {
  const location = useLocation();
  const [user, setUser] = useState(null);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [expiree, setExpiree] = useState(false);

  // Rechargement des stats, appelable a tout moment
  const rafraichirStats = useCallback(async () => {
    try { setStats(await api.stats()); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    let actif = true;
    api.me()
      .then(async (u) => {
        if (!actif) return;
        setUser(u);
        await rafraichirStats();
      })
      .catch(() => { if (actif) setUser(null); })
      .finally(() => { if (actif) setLoading(false); });
    return () => { actif = false; };
  }, [rafraichirStats]);

  // Session expirée côté serveur (401) : retour à la connexion, avec le message « Session expirée »,
  // puis retour à la page demandée après la reconnexion
  const userRef = useRef(null);
  userRef.current = user;
  useEffect(() => {
    const surExpiration = () => {
      if (!userRef.current) return;   // pas connecté (1er chargement, page de connexion)
      setExpiree(true);
      setUser(null);
    };
    window.addEventListener("lims:session-expiree", surExpiration);
    return () => window.removeEventListener("lims:session-expiree", surExpiration);
  }, []);

  if (loading) return <div className="loading">Chargement…</div>;

  if (!user) {
    const depuis = location.pathname === "/login" ? location.state?.depuis : location.pathname + location.search;
    return (
      <Routes>
        <Route path="/login" element={
          <Login expiree={expiree} onLogin={async (u) => { setExpiree(false); setUser(u); await rafraichirStats(); }} />
        } />
        <Route path="*" element={<Navigate to="/login" replace state={{ depuis }} />} />
      </Routes>
    );
  }

  const estAdmin = user.role === "admin";
  return (
    <Shell user={user} stats={stats} onLogout={() => setUser(null)}>
      <Routes>
        {/* Après la connexion : retour à la page demandée avant l'expiration de la session */}
        <Route path="/login" element={<Navigate to={location.state?.depuis || "/"} replace />} />
        <Route path="/" element={<Dashboard user={user} />} />
        <Route path="/travail" element={<Travail />} />
        <Route path="/equipements" element={<Equipements user={user} />} />
        <Route path="/controles-qualite" element={<ControlesQualite user={user} />} />
        <Route path="/habilitations" element={<Habilitations user={user} />} />
        <Route path="/reactifs" element={<Reactifs user={user} />} />
        <Route path="/requetes" element={<Requetes user={user} />} />
        <Route path="/bilan-mensuel" element={<BilanMensuel user={user} />} />
        <Route path="/facturation" element={
          ROLES_GLOBAUX.includes(user.role) ? <Facturation user={user} /> : <Navigate to="/" replace />
        } />
        <Route path="/echantillons" element={<Echantillons user={user} onChange={rafraichirStats} />} />
        <Route path="/echantillons/ajouter" element={<EchantillonForm />} />
        <Route path="/echantillons/modifier/:num" element={<EchantillonForm edition />} />
        <Route path="/echantillons/detail/:num" element={<EchantillonDetail user={user} />} />
        <Route path="/traitement/:section" element={<Traitement user={user} />} />
        <Route path="/resultats/:section" element={<Resultats user={user} />} />
        {/* Administration : un non-admin revient à l'accueil (pages connues, mais réservées) */}
        <Route path="/admin/users" element={estAdmin ? <Admin user={user} /> : <Navigate to="/" replace />} />
        <Route path="/admin/referentiels" element={estAdmin ? <Referentiels /> : <Navigate to="/" replace />} />
        <Route path="/admin/audit" element={estAdmin ? <Audit /> : <Navigate to="/" replace />} />
        <Route path="*" element={<PageIntrouvable />} />
      </Routes>
    </Shell>
  );
}
