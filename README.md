# Gestion de cabinet médical

Application locale Django/PostgreSQL pour un cabinet de deux médecins. Les modules disponibles sont la connexion médecin, le tableau de bord, la gestion des fiches patients, l’historique des consultations et le suivi financier des factures et paiements. Aucun rôle secrétaire n'est activé.

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

Connectez-vous sur http://localhost:8001/ avec un compte médecin. Vous pouvez créer et modifier des dossiers fictifs, les rechercher par nom, CIN, téléphone ou numéro de dossier, consulter leurs informations et archiver/restaurer les dossiers sans les supprimer. N'utilisez aucune vraie donnée médicale pour les essais.

## Facturation et paiements

Depuis la navigation **Facturation** ou la fiche d'un patient, créez une facture en indiquant le patient, la date de consultation, le montant en TND et, facultativement, la date limite. Sur la facture, ajoutez des paiements partiels ou complets en précisant la date, le moyen et la référence. Le montant payé, le solde et le statut (non réglée, différée, partiellement réglée, réglée ou en retard) sont calculés à partir des paiements enregistrés. Les paiements supérieurs au solde sont refusés; les règlements sont conservés dans l'historique et ne sont pas modifiables depuis l'administration.

## Consultations et assurance

Créez une consultation depuis la fiche d’un patient ou le menu **Consultations**. Le médecin peut enregistrer avant l’assurance et la facturation l’examen clinique (TA, température, GAD, SpO2, FC et autres observations), l’acte médical ou la conduite à tenir, les examens complémentaires et la destination du malade. Ces informations figurent dans le détail de la consultation. Chaque nouvelle consultation reçoit sa propre facture. Le badge de paiement et le solde proviennent des transactions de cette facture; un statut de paiement n’est jamais saisi manuellement. Les informations d’assurance sont enregistrées par consultation. « Remplie » exige que l’assurance soit déclarée, que le dossier soit déclaré rempli, que le type, l’organisme et l’affiliation soient saisis, et que le médecin confirme la vérification.

Une consultation peut être modifiée depuis sa page de détail. Le patient associé reste fixe; la date, le motif, les informations cliniques, le prix et les informations d’assurance peuvent être ajustés. Les transactions existantes sont conservées et le nouveau prix ne peut pas être inférieur au total déjà payé. Toute modification des informations d’assurance nécessite une nouvelle vérification pour conserver le statut « Remplie ».

Les formulaires de consultation proposent une auto-complétion pour le motif, l’acte médical, la conduite à tenir, les examens biologiques et d’imagerie, les autres examens et la destination. Pour les champs à valeurs multiples (motifs, actes, conduite et examens), appuyez sur Entrée pour créer une étiquette; supprimez-la avec × ou retirez la dernière avec Retour arrière lorsque le champ est vide. Les suggestions peuvent aussi être sélectionnées au clavier ou à la souris. Les recherches ignorent les accents et la casse, les doublons sont ignorés et la saisie libre reste possible. Les valeurs sont conservées sur plusieurs lignes dans le dossier, sans modifier les anciennes valeurs déjà enregistrées. La page **Suggestions** permet à chaque médecin d’ajouter, modifier et archiver ses propres propositions; une bibliothèque commune est aussi fournie. Les choix sont classés selon leur fréquence d’utilisation.

Les anciennes factures sans dossier de consultation restent intactes dans le module de facturation. Elles ne sont pas transformées en consultations fictives.

## Impression et export PDF

Depuis le dossier d’un patient, utilisez **Imprimer la fiche patient** pour obtenir son identité, ses informations médicales, l’historique des consultations et la situation de facturation. Depuis le détail d’une consultation, **Imprimer le compte rendu** génère le compte rendu médical. Depuis le détail d’une facture, **Imprimer la facture** affiche les montants et paiements; chaque paiement dispose de sa propre action **Imprimer le reçu**.

Chaque action ouvre un aperçu HTML imprimable. Utilisez **Imprimer** pour l’impression du navigateur ou **Télécharger le PDF** pour enregistrer le PDF. Les montants, soldes et statuts sont calculés à l’affichage à partir des paiements existants; aucune donnée financière n’est modifiée. Les factures historiques sans consultation restent imprimables. Aucune migration ni table n’est ajoutée.

Le logo du document est lu depuis `static\img\logo_cabinet.jpg`. Placez-y votre image pour l’afficher; elle n’est ni générée ni modifiée par l’application. Les polices Cormorant Garamond et Noto Naskh Arabic sont fournies localement avec leurs licences SIL OFL. La génération PDF utilise les bibliothèques Pango/HarfBuzz du conteneur Docker.

Pour reconstruire et démarrer sous Windows :

```powershell
docker compose build web
docker compose up -d
docker compose run --rm --no-deps web python manage.py test --settings=cabinet_config.test_settings
```

Après démarrage, ouvrez `http://localhost:8001/`, connectez-vous, puis vérifiez l’aperçu et le téléchargement depuis les pages patient, consultation et facture. Le PDF téléchargé s’ouvre avec le lecteur PDF de Windows ou le navigateur. Les tests qui génèrent les PDF doivent être lancés dans Docker, où Pango et HarfBuzz sont installés.

Arrêter l'application avec `Ctrl+C`, ou depuis un autre terminal avec `docker compose down`. Cette commande conserve le volume PostgreSQL; ne pas supprimer ce volume sans sauvegarde vérifiée.

## Vérification

```powershell
.\.venv\Scripts\python.exe manage.py test accounts patients core billing consultations --settings=cabinet_config.test_settings
docker compose exec web python manage.py check
```

Les tests unitaires utilisent une base SQLite temporaire; l'application configurée et lancée avec Compose utilise PostgreSQL. Pour inclure les tests PDF, utilisez la commande Docker de la section **Impression et export PDF**. Les données de démonstration réelles ne sont pas incluses. Utiliser uniquement des identités fictives pour les essais.

## Installation automatique sur le PC du médecin

L’installateur Windows se construit depuis le poste de développement avec le SDK .NET 8 et Inno Setup 6 installés. Il est généré par `windows\Build-Installer.ps1`, puis le fichier `windows\distribution\Cabinet-Setup-1.0.0.exe` peut être remis au médecin. Le paquet comprend uniquement le code et les ressources nécessaires; le fichier `.env` du poste de développement et la base locale ne sont jamais copiés.

Sur le PC du médecin, installer Docker Desktop pour Windows en mode conteneurs Linux, puis exécuter `Cabinet-Setup-1.0.0.exe`. L’installation crée un raccourci sur le Bureau, mais aucun lancement automatique au démarrage de Windows. L’installateur propose de démarrer Cabinet à la fin de l’installation; ensuite, cliquer sur **Cabinet médical** sur le Bureau suffit. Au premier lancement, Cabinet attend Docker, démarre PostgreSQL et Django, puis demande une seule fois les identifiants du médecin. Le mot de passe doit contenir au moins 8 caractères et ne pas être courant, uniquement numérique ou similaire aux informations personnelles du compte. En cas d’erreur lors de la création du compte, le lanceur affiche le détail et permet de réessayer sans perdre les informations saisies. Les lancements suivants ouvrent directement l’écran de connexion dans Microsoft Edge en mode application.

Windows peut afficher **« Microsoft Defender SmartScreen a empêché le démarrage d’une application non reconnue »** pour cet installateur non signé. Pour supprimer cet avertissement de façon légitime, il faut signer l’installateur avec un certificat de signature de code reconnu; modifier l’application ne permet pas de supprimer sûrement cet avertissement. En attendant, ne lancer le fichier que si sa provenance et son intégrité ont été vérifiées. Si vous choisissez de continuer, utilisez **Informations complémentaires**, puis **Exécuter quand même**; ne désactivez pas SmartScreen ni Microsoft Defender.

La base PostgreSQL est conservée dans un volume Docker nommé et la configuration secrète dans `%LOCALAPPDATA%\Cabinet`. La désinstallation arrête les conteneurs sans supprimer leur volume et laisse la configuration à sa place afin de préserver les données lors d’une réinstallation. Cette installation est destinée au compte Windows du médecin; utiliser un autre compte Windows ne retrouvera pas automatiquement sa configuration. N’utilisez jamais `docker compose down -v` : cette option supprime les volumes et les dossiers médicaux. Les sauvegardes de la base doivent être planifiées et testées séparément.

Le serveur utilise Gunicorn et sert les fichiers statiques avec WhiteNoise. L’application reste liée à `127.0.0.1:8001`; elle n’est pas publiée sur le réseau du cabinet. Si Docker Desktop n’est pas installé ou si le moteur ne démarre pas, Cabinet affiche une erreur au lieu de réinitialiser la base.
