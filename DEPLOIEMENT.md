# Déploiement de Spectre sur un serveur (Docker)

On construit l'image **sur ton poste**, on l'envoie au serveur en `.tar`, et on la lance avec
`docker compose up -d`. Le serveur n'a besoin d'aucun accès à GitHub ni au GitLab interne.

Hypothèses : serveur Linux avec Docker + le plugin Compose (`docker compose version` répond), accessible en SSH ;
`SERVEUR` = son nom ou son IP, `TOI` = ton compte SSH.

## 1. Sur ton poste Windows : construire l'image

1. Lancer **Docker Desktop** (attendre qu'il soit « running »).
2. **Une seule fois** — certificat de l'entreprise : le GitLab interne est signé par une autorité inconnue de l'image.
   Exporter le certificat racine Aledia (Windows : `certmgr.msc` ▸ Autorités de certification racines de confiance ▸ le
   certificat de l'entreprise ▸ clic droit ▸ Toutes les tâches ▸ Exporter ▸ « X.509 encodé en base 64 (.CER) »), le
   renommer en `.crt` et le déposer dans le dossier `certs\` du dépôt. Sans lui : `server verification failed:
   certificate signer not trusted`.
3. **Jeton GitLab** : les dépôts PRISM et Lumière sont privés. Créer un jeton d'accès personnel sur
   `gitlab-it.aledia.com` (Préférences ▸ Access tokens, portée `read_repository`) ; `build-docker.bat` le demande (ou lit la
   variable d'environnement `GITLAB_TOKEN`) et le passe à Docker comme secret de build : il n'est écrit nulle part dans l'image.
4. Double-cliquer `build-docker.bat` à la racine du dépôt (réseau d'entreprise nécessaire : il télécharge
   StructureForge sur GitHub et PRISM sur le GitLab interne).
5. Il produit le dossier `dist\` avec trois fichiers :
   - `spectre-image.tar` — l'image (ne contient aucun mot de passe) ;
   - `docker-compose.yml` ;
   - `.env.example`.

## 2. Envoyer les fichiers sur le serveur

Dans PowerShell, depuis la racine du dépôt :

```powershell
ssh TOI@SERVEUR "mkdir -p ~/spectre"
scp dist\spectre-image.tar dist\docker-compose.yml dist\.env.example TOI@SERVEUR:~/spectre/
```

## 3. Sur le serveur : préparer et lancer

```bash
ssh TOI@SERVEUR
cd ~/spectre
```

Charger l'image :

```bash
docker load -i spectre-image.tar
docker images spectre        # doit afficher spectre:latest
```

Créer le fichier de configuration `.env` (dans le même dossier que `docker-compose.yml`) :

```bash
cp .env.example .env
nano .env
```

À renseigner :

- `PRISM_USER` / `PRISM_PASSWORD` : le compte de lecture PRISM ;
- `SPECTRE_BASE_URL=http://SERVEUR:8000` (décommenter) : l'adresse que les utilisateurs taperont, utilisée dans les
  liens des e-mails. Si un reverse proxy fait du HTTPS, mettre l'URL `https://...` (le cookie de session passe alors en `Secure`) ;
- SMTP (optionnel) : sans lui, les e-mails d'invitation / mot de passe oublié ne partent pas — d'où la
  réinitialisation par l'administrateur (voir §6).

Protéger le fichier puis démarrer :

```bash
chmod 600 .env
docker compose up -d
```

Le port **8000** du serveur est publié (`"8000:8000"`). Si un pare-feu tourne (ex. `ufw allow 8000/tcp`), l'ouvrir.

## 4. Vérifier

```bash
docker compose ps                 # spectre : Up
docker compose logs -f spectre    # Ctrl+C pour quitter ; pas d'erreur au démarrage
curl -I http://localhost:8000/connexion   # HTTP/1.1 200
```

Depuis ton navigateur : `http://SERVEUR:8000`.

## 5. Premier compte administrateur

Au tout premier démarrage (volume `/data` vide), Spectre crée le compte :

| Identifiant | Mot de passe |
|-------------|--------------|
| `admin`     | `admin`      |

1. Ouvrir `http://SERVEUR:8000/connexion`, se connecter avec `admin` / `admin`.
2. Spectre redirige vers le **profil** et reste fermé tant qu'un nouveau mot de passe n'est pas choisi :
   mot de passe actuel = `admin`, puis le nouveau (8 caractères minimum). On est déconnecté, se reconnecter.
3. **Paramètres** (roue crantée) ▸ **Utilisateurs** : la liste des comptes.

Les autres personnes créent leur compte sur `/inscription` (ils ne sont pas administrateurs). Pour en promouvoir un :

```bash
docker compose exec spectre spectre admin prenom.nom@aledia.com
```

(le compte `admin` initial n'est créé que sur une base vide, jamais sur une base qui a déjà des comptes.)

## 6. Mot de passe oublié (administrateur)

**Paramètres ▸ Utilisateurs ▸ Réinitialiser le mot de passe** sur la ligne du compte :

1. Spectre génère un **mot de passe provisoire**, affiché **une seule fois** — le transmettre à la personne ;
2. le compte est déconnecté partout ;
3. à sa prochaine connexion avec ce mot de passe provisoire, Spectre l'oblige à en choisir un nouveau avant
   toute autre action.

## 7. Où mettre le volume `data` ?

`docker-compose.yml` déclare un **volume nommé** `spectre-data` monté sur `/data` dans le conteneur. Il contient la
base `spectre.db` (comptes, projets, études…), les dépôts d'expériences, les pièces jointes et les caches.

- **Rien à créer ni à choisir** : Docker le crée au premier `up`. Il vit dans `/var/lib/docker/volumes/spectre-data/_data`
  (accessible en `sudo`), il survit à `docker compose down`, à `up`, à un nouveau `docker load` d'une version plus récente.
  **Ne jamais** lancer `docker compose down -v` : l'option `-v` supprime le volume, donc toutes les données.
- **Sauvegarde** : dans Spectre, *Paramètres ▸ Base de données ▸ Sauvegarde* télécharge un ZIP de tout le dossier de données.
  À défaut, côté serveur :
  ```bash
  docker run --rm -v spectre-data:/data -v "$PWD":/backup alpine tar czf /backup/spectre-data-$(date +%F).tgz -C /data .
  ```
- **Variante : dossier choisi** (ex. un disque dédié `/srv/spectre/data`) à la place du volume nommé :
  ```bash
  sudo mkdir -p /srv/spectre/data && sudo chown 1000:1000 /srv/spectre/data   # le conteneur tourne en UID 1000
  ```
  puis dans `docker-compose.yml`, remplacer `- spectre-data:/data` par `- /srv/spectre/data:/data` et supprimer le bloc
  `volumes: spectre-data:` en bas du fichier.

## 8. Mettre à jour vers une nouvelle version

1. Poste Windows : relancer `build-docker.bat`, puis `scp dist\spectre-image.tar TOI@SERVEUR:~/spectre/`
   (et `docker-compose.yml` si le compose a changé).
2. Serveur :
   ```bash
   cd ~/spectre
   docker load -i spectre-image.tar
   docker compose up -d      # recrée le conteneur avec la nouvelle image ; les données restent
   ```
   Les migrations de base s'appliquent toutes seules au démarrage.

## Points d'attention

- **Réseau du conteneur** : les profils PRISM (`config/connections.yml`) visent les hôtes `INF49` et `INF10` ; le serveur
  doit les résoudre et joindre le port 5432. Test : `docker compose exec spectre python -c "import socket; print(socket.gethostbyname('INF49'))"`.
- **Images MEB / dossiers réseau** : les chemins du type `N:\...` n'existent pas dans un conteneur Linux. Pour les lire,
  monter le partage sur le serveur puis dans le compose (`volumes: - /mnt/meb:/mnt/meb:ro`) et poser
  `SPECTRE_EXTERNAL_IMAGE_ROOTS=/mnt/meb` ; sinon ces fonctions restent indisponibles.
- **Pas d'architecture croisée** : l'image est construite pour l'architecture de ton poste (amd64) — c'est celle du serveur ?
- **Arrêt / redémarrage** : `docker compose stop` / `docker compose start` ; le service redémarre seul après un reboot
  (`restart: unless-stopped`).
