# Cellwright : démarrage rapide

Le scanner Cellwright réalise un inventaire hors ligne sans exécuter les macros ni modifier les fichiers. Il fonctionne sans Office ni Python. Les outils facultatifs de conversion et le tableau de bord nécessitent Python ; les cibles UNO nécessitent LibreOffice.

```powershell
cellwright.exe scan C:\Finance --out .\rapports\finance --lang fr --no-source
cellwright.exe extract .\Budget.xlsm --out .\rapports\sources --lang fr
cellwright.exe rules list --lang fr
```

Le dossier de destination doit être nouveau ou vide. Le rapport HTML fonctionne hors ligne, avec recherche et tri. Les CSV et `scan.json` permettent une analyse complémentaire. `extract` exporte le code VBA et les sections M, avec un manifeste d’origine. Les fichiers `.frm` ne contiennent pas le concepteur de formulaire.

`--no-source` omet les sources VBA et M ; chemins, noms, références et constats restent visibles. `--skip-protected` ignore le VBA protégé ou de protection inconnue. Les fichiers chiffrés ne sont pas déchiffrés. La sortie `1` signale une inspection incomplète ; la sortie `2` une erreur de configuration ou de destination.

Les estimations sont des hypothèses non calibrées. Aucun obstacle connu ne garantit la compatibilité LibreOffice. La couverture XLS/XLSB reste partielle ; les contrôles UserForm sont inventoriés quand ils sont lisibles, sans conversion du concepteur. Les écarts source/cache sont des indices, pas une détection complète du VBA stomping.

```powershell
cellwright.exe serve --port 8768
cellwright.exe convert .\Budget.xlsm --out .\candidat --target basic
cellwright.exe migrate verify .\cas.json --out .\preuve --allow-execution
```

Le tableau de bord local est disponible sur http://127.0.0.1:8768 : historique, affectations, états et scans planifiés tant que le serveur fonctionne. La conversion conserve les originaux, différences et TODO. L’exécution est volontaire et réservée au code de confiance ; elle n’est pas isolée du système. Un cas réussi ne prouve que les entrées et cellules comparées. Les cibles Python et les requêtes M/pandas prennent en charge un sous-ensemble documenté dans `docs/migration.md`.

Pour compiler : Rust 1.99.0, puis `cargo build --locked --release`. Les règles et pondérations TOML sont illustrées dans `data/`. Voir le README anglais pour les limites et options complètes. Cette traduction n’a pas été relue par un locuteur natif.
