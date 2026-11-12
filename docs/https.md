# Servir l'application en HTTPS sur le réseau local

Sans HTTPS, le mot de passe et le cookie de session circulent en clair sur le réseau du laboratoire. Cette procédure met l'application en HTTPS avec **uvicorn seul**, qui sait servir du TLS.

> Ce document ne fait que décrire la procédure. Rien n'est installé automatiquement.

Les outils utilisés sont déjà présents sur un poste de développement Windows :
- `openssl`, fourni avec Git for Windows (`C:\Program Files\Git\usr\bin\openssl.exe`) ;
- PowerShell ;
- le venv de l'application.

---

## 1. Choisir le nom du serveur

Les postes doivent joindre le serveur par un nom ou une adresse **fixe**, qui sera inscrit dans le certificat. Par exemple :

- nom : `lims.lrarvy.local` (enregistrement DNS interne, ou ligne dans le fichier `hosts` de chaque poste) ;
- adresse : `192.168.1.20` (IP fixe ou réservation DHCP).

Dans la suite, remplacez `lims.lrarvy.local` et `192.168.1.20` par vos valeurs.

## 2. Créer une autorité interne et le certificat du serveur

Une petite autorité de certification (AC) interne évite les alertes de sécurité. On installe son certificat sur chaque poste, et tous les certificats qu'elle signe sont reconnus.

Dans un dossier protégé du serveur, par exemple `D:\LIMS\tls` (accès réservé aux administrateurs), lancez dans **Git Bash** :

```bash
cd /d/LIMS/tls

# 2.1 Autorité interne (10 ans) : garder ac-lims.key en lieu sûr
openssl req -x509 -newkey rsa:3072 -sha256 -days 3650 -nodes \
  -keyout ac-lims.key -out ac-lims.crt -subj "/CN=AC interne LRARVY/O=ONSSA LRAR Tanger"

# 2.2 Clé et demande du serveur
openssl req -newkey rsa:2048 -sha256 -nodes \
  -keyout serveur.key -out serveur.csr -subj "/CN=lims.lrarvy.local"

# 2.3 Certificat du serveur (2 ans) avec les noms et l'adresse acceptés
printf "subjectAltName=DNS:lims.lrarvy.local,IP:192.168.1.20\nextendedKeyUsage=serverAuth\n" > ext.cnf
openssl x509 -req -in serveur.csr -CA ac-lims.crt -CAkey ac-lims.key -CAcreateserial \
  -days 730 -sha256 -extfile ext.cnf -out serveur.crt
```

Le serveur a besoin de deux fichiers : `serveur.key` et `serveur.crt`. Ne partagez **jamais** `serveur.key` ni `ac-lims.key`.

## 3. Faire reconnaître l'autorité par les postes

Sur chaque poste client, en PowerShell **administrateur** :

```powershell
Import-Certificate -FilePath "\\serveur\partage\ac-lims.crt" -CertStoreLocation Cert:\LocalMachine\Root
```

Pour un parc géré par un domaine, on peut le faire une seule fois par stratégie de groupe : *Configuration ordinateur > Paramètres Windows > Paramètres de sécurité > Stratégies de clé publique > Autorités de certification racines de confiance*.

Firefox a son propre magasin de certificats. Dans `about:config`, mettez `security.enterprise_roots.enabled` à `true`, ou importez `ac-lims.crt` dans ses paramètres.

## 4. Lancer l'application en HTTPS

Dans PowerShell, depuis `backend\` avec le venv activé :

```powershell
$env:SESSION_HTTPS = "1"          # cookie de session « Secure » : envoyé uniquement en HTTPS
$env:SECRET_KEY = "<longue valeur aléatoire>"   # voir § 6
uvicorn app.main:app --host 0.0.0.0 --port 443 `
  --ssl-keyfile D:\LIMS\tls\serveur.key --ssl-certfile D:\LIMS\tls\serveur.crt
```

- L'adresse devient `https://lims.lrarvy.local/`. Le front est servi par FastAPI depuis `frontend/dist`, après `npm run build`.
- Écouter sur le port 443 demande que le service tourne avec un compte autorisé. Sinon, utilisez par exemple `--port 8443` et l'adresse `https://lims.lrarvy.local:8443/`.
- Pare-feu Windows : autorisez le port choisi en entrée, réseau privé uniquement :

```powershell
New-NetFirewallRule -DisplayName "LIMS HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Profile Private -Action Allow
```

- La protection CSRF compare l'en-tête `Origin` à l'hôte appelé, donc elle fonctionne sans réglage en HTTPS. La variable `ORIGINES_AUTORISEES` ne sert que si une autre adresse doit appeler l'API, comme le serveur Vite de développement.

## 5. Vérifier

1. Depuis un poste, ouvrez `https://lims.lrarvy.local/` : le cadenas s'affiche, sans alerte.
2. Après la connexion, dans les outils de développement (F12 > Application > Cookies), le cookie `session` a les attributs `Secure` et `SameSite=Lax`.
3. En `http://`, l'application n'est plus accessible, puisque uvicorn n'écoute plus qu'en HTTPS.

## 6. Points à régler avant la mise en production

- **`SECRET_KEY`** signe les cookies de session. La valeur par défaut de `app/core/config.py` (`change-me-en-production`) doit être remplacée par une valeur longue et aléatoire, passée par variable d'environnement. Pour la générer :
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- **Mot de passe PostgreSQL** : la valeur par défaut de `DATABASE_URL` dans `config.py` contient le mot de passe en clair. En production, définissez `DATABASE_URL` en variable d'environnement du service, et changez ce mot de passe.
- **Mots de passe des comptes** : la règle (au moins 10 caractères, avec lettres et chiffres) s'applique à chaque création ou changement. Les comptes existants dont le mot de passe est plus faible doivent le changer (bouton « Mot de passe » de l'en-tête), ou l'admin doit le réinitialiser.
- **Renouvellement** : le certificat du serveur expire au bout de 2 ans. Refaites les étapes 2.2 et 2.3 avant l'échéance (l'autorité reste valable), puis redémarrez uvicorn.

## 7. Réglages de sécurité de l'application (rappel)

| Variable d'environnement | Rôle | Défaut |
|---|---|---|
| `SESSION_INACTIVITE_MIN` | déconnexion après N minutes sans activité | `30` |
| `SESSION_HTTPS` | cookie `Secure` (à mettre à `1` en HTTPS) | `0` |
| `ORIGINES_AUTORISEES` | autres origines admises pour les requêtes d'écriture (CSRF) | `http://localhost:5173,http://127.0.0.1:5173` |
| `SECRET_KEY` | signature des cookies de session | à définir |
| `DATABASE_URL` | connexion PostgreSQL | à définir |

La durée maximale d'une session reste de 8 heures (`SESSION_MAX_AGE`). Un compte est verrouillé 15 minutes après 5 échecs de connexion consécutifs ; l'admin peut le déverrouiller depuis l'écran Comptes.
