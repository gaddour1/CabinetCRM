# Gestion de cabinet médical

Application locale Django/PostgreSQL pour un cabinet médical. Les modules disponibles sont la connexion médecin, le tableau de bord, la gestion des fiches patients, l’historique des consultations et les ordonnances médicales. Aucun rôle secrétaire n'est activé.

## Démarrage sous Windows

1. Installer Docker Desktop et démarrer son moteur.
2. Depuis PowerShell, dans le dossier du projet :

   ```powershell
   Copy-Item .env.example .env
   ```
3. Remplacer les valeurs de `DJANGO_SECRET_KEY` et `POSTGRES_PASSWORD` dans `.env`.
4. Construire et démarrer les services :

   ```powershell
   docker compose up --build
   ```

   Les migrations sont appliquées au démarrage. L'application médecin est disponible à l'adresse http://localhost:8001/ et l'administration à l'adresse http://localhost:8001/admin/.
5. Dans un autre terminal, créer le compte administrateur :

   ```powershell
   docker compose exec web python manage.py createsuperuser
   ```

   La commande crée un compte de rôle administrateur. Créez les comptes médecins depuis l'administration et donnez-leur un mot de passe temporaire; chaque médecin peut ensuite se connecter à l'interface principale.

## Module patients

Connectez-vous sur http://localhost:8001/ avec un compte médecin. Vous pouvez créer et modifier des dossiers, consulter l’âge calculé depuis la date de naissance, les rechercher, et archiver/restaurer les dossiers. La suppression d’un patient demande confirmation et supprime aussi définitivement ses consultations.

## Consultations et assurance

Créez une consultation depuis la fiche d’un patient ou le menu **Consultations**. Le prix de la consultation peut être renseigné, mais il est facultatif. Le médecin peut également enregistrer l’examen clinique (TA, température, GAD, SpO2, FC et autres observations), l’acte médical ou la conduite à tenir, les examens complémentaires et la destination du malade. Ces informations figurent dans le détail de la consultation. Les informations d’assurance sont enregistrées par consultation. « Remplie » exige que l’assurance soit déclarée, que le dossier soit déclaré rempli, que le type, l’organisme et l’affiliation soient saisis, et que le médecin confirme la vérification.

Une consultation peut être modifiée depuis sa page de détail. Le patient associé reste fixe; la date, le motif, les informations cliniques, le prix facultatif et les informations d’assurance peuvent être ajustés. Toute modification des informations d’assurance nécessite une nouvelle vérification pour conserver le statut « Remplie ». La suppression d’une consultation demande confirmation.

Les formulaires de consultation proposent une auto-complétion pour le motif, l’acte médical, la conduite à tenir, les examens biologiques et d’imagerie, les autres examens et la destination. Pour les champs à valeurs multiples (motifs, actes, conduite et examens), appuyez sur Entrée pour créer une étiquette; supprimez-la avec × ou retirez la dernière avec Retour arrière lorsque le champ est vide. Les suggestions peuvent aussi être sélectionnées au clavier ou à la souris. Les recherches ignorent les accents et la casse, les doublons sont ignorés et la saisie libre reste possible. Les valeurs sont conservées sur plusieurs lignes dans le dossier, sans modifier les anciennes valeurs déjà enregistrées. La page **Suggestions** permet à chaque médecin d’ajouter, modifier et archiver ses propres propositions; une bibliothèque commune est aussi fournie. Les choix sont classés selon leur fréquence d’utilisation.

## Ordonnances médicales

Dans le formulaire de consultation, le médecin peut rédiger une ordonnance facultative avec plusieurs médicaments, les réorganiser et enregistrer un brouillon. Les noms suggérés proviennent uniquement de sa bibliothèque personnelle; une saisie libre reste possible. Les informations de prescription (posologie, fréquence et durée) doivent être saisies par le médecin et ne sont jamais déduites du nom. Une ordonnance validée est protégée contre les modifications directes. Toute correction exige un motif et conserve une copie de la version précédente. Le dossier patient donne accès à l’historique, à l’aperçu imprimable et au téléchargement PDF.

La migration `prescriptions/0001_initial.py` ajoute uniquement les tables du module d’ordonnances; elle ne supprime ni ne réinitialise les données existantes. Compose applique les migrations au démarrage. Pour l’appliquer manuellement après une sauvegarde :

```powershell
docker compose exec web python manage.py migrate prescriptions
```

## Impression et export PDF

Depuis le dossier d’un patient, utilisez **Imprimer la fiche patient** pour obtenir son identité, son âge, ses informations médicales et l’historique des consultations. Depuis le détail d’une consultation, **Imprimer le compte rendu** génère le compte rendu médical.

Chaque action ouvre un aperçu HTML imprimable. Utilisez **Imprimer** pour l’impression du navigateur ou **Télécharger le PDF** pour enregistrer le PDF.

Le logo du document est lu depuis `static\img\logo_cabinet.jpg`. Placez-y votre image pour l’afficher; elle n’est ni générée ni modifiée par l’application. Les polices Cormorant Garamond et Noto Naskh Arabic sont fournies localement avec leurs licences SIL OFL. La génération PDF utilise les bibliothèques Pango/HarfBuzz du conteneur Docker.

Pour reconstruire et démarrer sous Windows :

```powershell
docker compose build web
docker compose run --rm --no-deps --entrypoint python web manage.py test --settings=cabinet_config.test_settings
docker compose up -d
```

Après démarrage, ouvrez `http://localhost:8001/`, connectez-vous, puis vérifiez l’aperçu et le téléchargement depuis les pages patient et consultation. Le PDF téléchargé s’ouvre avec le lecteur PDF de Windows ou le navigateur. Les tests qui génèrent les PDF doivent être lancés dans Docker, où Pango et HarfBuzz sont installés.

Arrêter l'application avec `Ctrl+C`, ou depuis un autre terminal avec `docker compose down`. Cette commande conserve le volume PostgreSQL; ne pas supprimer ce volume sans sauvegarde vérifiée.

## Vérification

```powershell
.\.venv\Scripts\python.exe manage.py test accounts patients core consultations documents prescriptions --settings=cabinet_config.test_settings
docker compose exec web python manage.py check
```

Les tests unitaires utilisent une base SQLite temporaire; l’application configurée et lancée avec Compose utilise PostgreSQL. Sous Windows, les tests PDF nécessitent les bibliothèques Pango/HarfBuzz du conteneur. Utilisez la commande Docker ci-dessus avec `--entrypoint python` : elle contourne l’entrypoint de démarrage et n’exécute pas de migrations sur la base de développement. Les données de démonstration réelles ne sont pas incluses. Utiliser uniquement des identités fictives pour les essais.

La migration qui retire le module de facturation ne supprime pas physiquement les anciennes tables `billing_invoice` et `billing_payment`. Elles sont conservées dans PostgreSQL pour préserver l’historique des factures et paiements. Le contrôle `check_migrations_safe` bloque le démarrage si une migration en attente contient une opération destructive non approuvée. N’ignorez jamais ce blocage sur une base contenant des données médicales.

## Installation automatique sur le PC du médecin

L’installateur Windows V2 se construit depuis le poste de développement avec le SDK .NET 8 et Inno Setup 6 installés :

```powershell
.\windows\Build-Installer.ps1
```

Le résultat attendu est `windows\distribution\Cabinet-Setup-2.0.0.exe`. Le script compose une liste explicite de fichiers applicatifs, inclut `.env.example`, puis refuse d’empaqueter des fichiers `.env`, des bases locales ou des sauvegardes. Vérifiez le contenu du paquet avant toute distribution. Ne copiez jamais le `.env` du développeur, un volume Docker, une sauvegarde ou des dossiers contenant des documents patients.

Pour une première installation, installer Docker Desktop en mode conteneurs Linux, puis exécuter `Cabinet-Setup-2.0.0.exe`. Le raccourci **Cabinet médical** est créé sur le Bureau; aucun démarrage automatique à l’ouverture de Windows n’est configuré. Le premier lancement vérifie Docker, refuse de réutiliser un volume PostgreSQL non identifié, démarre le projet `cabinet`, puis demande une seule fois les identifiants du médecin. Les lancements suivants ouvrent l’application dans Microsoft Edge en mode application.

## Mise à jour V1 vers V2

La mise à jour doit être effectuée sous le même compte Windows et dans le dossier d’installation existant. L’installateur V2 reconnaît l’installation précédente via son enregistrement Windows et annule l’opération si le dossier change ou si l’installation/configuration est incohérente. Avant de remplacer le moindre fichier, le lanceur V1 :

1. Vérifie que le conteneur PostgreSQL est démarré, que le volume persistant est monté et que son étiquette Compose correspond au projet détecté.
2. Vérifie que PostgreSQL répond et que les tables historiques des factures et paiements sont présentes.
3. Crée hors du volume une sauvegarde `pg_dump` au format custom et une sauvegarde des rôles `pg_dumpall --globals-only`; vérifie que les fichiers ne sont pas vides, que l’archive peut être listée et que les rôles sont inclus; écrit un manifeste avec la version, le volume, et les empreintes SHA-256.
4. Enregistre le nom du projet Compose détecté, puis arrête proprement les services sans supprimer les conteneurs ni les volumes.

Si une de ces étapes échoue, l’installation est annulée. Les éventuels fichiers de sauvegarde sont laissés dans `%LOCALAPPDATA%\Cabinet\backups`; ils ne sont jamais effacés automatiquement. Ne poursuivez pas manuellement l’installation et contactez le support. La sauvegarde des rôles dépend des permissions de PostgreSQL; un échec d’autorisation bloque volontairement la mise à jour.

Après vérification de la sauvegarde, Inno Setup remplace les fichiers du code au même emplacement. Au démarrage, Cabinet réutilise le projet Compose et le nom de volume enregistrés, compare le volume réel à la configuration avant de démarrer PostgreSQL, puis vérifie à nouveau le montage avant de démarrer Django. Il exécute ensuite `check_migrations_safe`, applique les migrations et attend la disponibilité HTTP. Les migrations peuvent ajouter de nouvelles tables, mais les opérations destructrices non explicitement reconnues sont bloquées. Ne lancez jamais `docker compose down -v`, `docker volume prune` ni une commande qui recrée le volume. Ne remplacez pas le `.env` sous `%LOCALAPPDATA%\Cabinet`.

Si Django ne démarre pas après une migration, conservez la sauvegarde et le journal Docker; ne désinstallez pas Cabinet et ne restaurez pas automatiquement par-dessus une base qui a pu recevoir de nouvelles données. Notez le message d’erreur et contactez le support. Après vérification de l’état et de la sauvegarde, le support pourra faire réinstaller l’ancienne version dans le même dossier ou restaurer une copie isolée avant de choisir une reprise. La restauration sur la base active ne doit avoir lieu qu’après décision explicite et vérification qu’aucune nouvelle donnée n’a été créée.

### Contrôles de sauvegarde et restauration (environnement de test seulement)

Les sauvegardes de mise à jour restent dans `%LOCALAPPDATA%\Cabinet\backups`. Le fichier `.dump` est un archive `pg_dump` custom; le fichier `*-globals.sql` contient les rôles. Vérifiez leurs tailles, le manifeste et les empreintes avant de les déplacer vers un support protégé. Testez régulièrement une restauration sur un PostgreSQL isolé et fictif, jamais sur la base de production :

```powershell
pg_restore --list .\cabinet-v1-before-v2.dump
createdb cabinet_restore_test
pg_restore --no-owner --no-acl --dbname cabinet_restore_test .\cabinet-v1-before-v2.dump
```

La restauration des rôles doit également être testée dans une instance isolée et nécessite les privilèges PostgreSQL appropriés. Ces commandes sont des exemples opérés par l’administrateur; le médecin ne doit pas les exécuter sur sa base active.

## Publication manuelle sur GitHub

Avant le commit, vérifier la branche, les fichiers suivis et les exclusions. `git status` et la vérification des fichiers sont obligatoires; ne pas ajouter de dumps, de `.env`, de fichiers patients ou de documents médicaux.

```powershell
git status --short --branch
git ls-files
git check-ignore -v .env .\backups\exemple.dump
git diff --check
git add .
git diff --cached --stat
git diff --cached --name-only
git commit -m "feat: release Cabinet V2"
git tag -a v2.0.0 -m "Cabinet V2"
```

Ces commandes préparent une publication locale uniquement. Après relecture des fichiers indexés et confirmation explicite, publier manuellement sur la branche principale configurée et envoyer le tag. Aucun push n’est effectué automatiquement par le projet ou par le script de build.

Avant une distribution, tester la mise à jour V1→V2 sur un PostgreSQL Docker isolé avec des patients, consultations, factures et paiements fictifs. Comparer les lignes et relations avant/après, vérifier l’empreinte du volume et tester la restauration de la sauvegarde. Ne jamais utiliser les données du médecin pour le test.

Windows peut afficher **« Microsoft Defender SmartScreen a empêché le démarrage d’une application non reconnue »** pour cet installateur non signé. Pour supprimer cet avertissement de façon légitime, il faut signer l’installateur avec un certificat de signature de code reconnu; modifier l’application ne permet pas de supprimer sûrement cet avertissement. En attendant, ne lancer le fichier que si sa provenance et son intégrité ont été vérifiées. Si vous choisissez de continuer, utilisez **Informations complémentaires**, puis **Exécuter quand même**; ne désactivez pas SmartScreen ni Microsoft Defender.

La base PostgreSQL est conservée dans un volume Docker nommé et la configuration secrète dans `%LOCALAPPDATA%\Cabinet`. La désinstallation arrête les conteneurs sans supprimer leur volume et laisse la configuration à sa place afin de préserver les données lors d’une réinstallation. Cette installation est destinée au compte Windows du médecin; utiliser un autre compte Windows ne retrouvera pas automatiquement sa configuration. N’utilisez jamais `docker compose down -v` : cette option supprime les volumes et les dossiers médicaux. Les sauvegardes de la base doivent être planifiées et testées séparément.

Le serveur utilise Gunicorn et sert les fichiers statiques avec WhiteNoise. L’application reste liée à `127.0.0.1:8001`; elle n’est pas publiée sur le réseau du cabinet. Si Docker Desktop n’est pas installé ou si le moteur ne démarre pas, Cabinet affiche une erreur au lieu de réinitialiser la base.
