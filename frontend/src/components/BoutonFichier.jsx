import { useState } from "react";
import { App, Button } from "antd";
import { api } from "../api/client";

// Bouton qui ouvre (PDF, nouvel onglet) ou télécharge (Excel, CSV) un fichier de l'API.
// Jamais de lien direct vers /api : en démonstration en ligne, l'authentification passe par un jeton
// que seul fetch peut transmettre (voir api.ouvrirFichier).
export default function BoutonFichier({ url, telecharger = false, nom, apres, children, ...props }) {
  const { message } = App.useApp();
  const [envoi, setEnvoi] = useState(false);
  const ouvrir = async () => {
    setEnvoi(true);
    try {
      await api.ouvrirFichier(url, { telecharger, nom });
      apres?.();
    } catch (e) {
      message.error(e.message);
    } finally {
      setEnvoi(false);
    }
  };
  return <Button {...props} loading={envoi} onClick={ouvrir}>{children}</Button>;
}
