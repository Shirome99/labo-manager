import { useEffect, useRef } from "react";
import { useBlocker } from "react-router-dom";
import { App } from "antd";

/**
 * Avertissement avant de quitter un formulaire modifié et non enregistré (tâche 31) :
 *  - navigation dans l'application (menu, liens, Précédent / Suivant, changement de ?num=) :
 *    confirmation « Quitter sans enregistrer ? » ;
 *  - fermeture ou rechargement de l'onglet : alerte du navigateur (beforeunload).
 * Renvoie :
 *  - liberer()            à appeler juste avant une navigation voulue (après un enregistrement) ;
 *  - confirmerAbandon(fn) exécute fn, après confirmation si le formulaire est modifié
 *                         (ex. choix d'un autre échantillon dans la même page).
 */
export function useAvertissementSortie(modifie) {
  const { modal } = App.useApp();
  const ref = useRef(modifie);
  ref.current = modifie;
  const ouverte = useRef(false);     // une seule confirmation à la fois (un clic peut bloquer deux navigations)

  const blocker = useBlocker(({ currentLocation, nextLocation }) => ref.current
    && (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search));

  const demander = (onOk, onCancel) => {
    if (ouverte.current) return;
    ouverte.current = true;
    modal.confirm({
      title: "Quitter sans enregistrer ?",
      content: "Les modifications de ce formulaire n'ont pas été enregistrées : elles seront perdues.",
      okText: "Quitter sans enregistrer", okButtonProps: { danger: true }, cancelText: "Rester sur la page",
      onOk: () => { ouverte.current = false; onOk(); },
      onCancel: () => { ouverte.current = false; onCancel?.(); },
    });
  };

  useEffect(() => {
    if (blocker.state === "blocked") demander(() => { ref.current = false; blocker.proceed(); }, () => blocker.reset());
  }, [blocker.state]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!modifie) return undefined;
    const avant = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", avant);
    return () => window.removeEventListener("beforeunload", avant);
  }, [modifie]);

  return {
    liberer: () => { ref.current = false; },
    confirmerAbandon: (fn) => (ref.current ? demander(() => { ref.current = false; fn(); }) : fn()),
  };
}
