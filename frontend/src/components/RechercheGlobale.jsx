import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Input } from "antd";
import { BarcodeOutlined } from "@ant-design/icons";
import { api } from "../api/client";

/**
 * Recherche globale de la topbar, compatible douchette (qui tape le code puis Entrée) :
 * un n° d'échantillon exact ouvre directement la fiche détail ; sinon, liste filtrée (?q=…).
 */
export default function RechercheGlobale() {
  const navigate = useNavigate();
  const [valeur, setValeur] = useState("");
  const [recherche, setRecherche] = useState(false);
  const champ = useRef(null);

  const chercher = async () => {
    const saisie = valeur.trim();
    if (!saisie || recherche) return;
    setRecherche(true);
    try {
      const e = await api.echantillon(saisie);       // n° exact
      navigate(`/echantillons/detail/${encodeURIComponent(e.num_echantillon)}`);
    } catch {
      navigate(`/echantillons?q=${encodeURIComponent(saisie)}`);
    } finally {
      setRecherche(false);
      setValeur("");
      champ.current?.blur();
    }
  };

  return (
    <Input
      ref={champ}
      size="small"
      className="recherche-globale"
      prefix={<BarcodeOutlined />}
      placeholder="N° ou scan…"
      value={valeur}
      onChange={(ev) => setValeur(ev.target.value)}
      onPressEnter={chercher}
      allowClear
      aria-label="Rechercher un échantillon ou scanner une étiquette"
    />
  );
}
