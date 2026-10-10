# Language support

The local dashboard supports English (`en`), French (`fr`) and German (`de`). Its language selector changes navigation, forms, buttons, statuses, setup guidance, conversion/checklist summaries and finding text. Dates and displayed numbers follow the selected language using the browser's regional formatting. Translations are bundled with the application and require no network service or API key.

On first use, the dashboard chooses a supported browser language, falling back to English. A saved selection takes precedence on later visits in that browser. If browser storage is unavailable, language switching still works for the current visit. The choice applies to this local dashboard, rather than to the public website or spreadsheet data.

Date and number formatting retain a matching browser region, including `en-GB`, `fr-CA` and `de-CH`, after saving or switching languages. If the browser has no regional preference for the selected language, formatting defaults to `en-US`, `fr-FR` or `de-DE`.

New scan and schedule forms default their report language to the interface language, and let you choose another. The demonstration scan uses the interface language. Each schedule stores its report language; schedules created before this feature use English. Changing the interface language updates finding text in the workspace without rewriting stored scan data or existing exported reports. CLI reports still use `--lang en|fr|de`.

The feature is included in the [v0.1.2 preview](https://github.com/scottcampbelldata/Cellwright/releases/tag/v0.1.2) and later builds. The public website and most documentation remain in English; [French](fr/quickstart.md) and [German](de/quickstart.md) quick-start guides are available.

## Coverage and limits

Workbook paths, worksheet/module/routine names, source code, provider names, rule IDs and user-entered labels stay as supplied. Process output, third-party errors, uncommon diagnostics and untranslated custom-rule messages may remain in their original language. Missing translation keys fall back to English. A translated conversion candidate or successful comparison retains the same scope and evidence requirements as its English version; changing language never enables macro execution.

Interface translation does not establish regional spreadsheet conversion compatibility. M type conversion currently accepts an omitted culture, `en-US` or `en-GB`; other explicit cultures fail for manual review. Supported UNO number-format conversion uses canonical `en-US` format codes. Regional date parsing, decimal coercion, localized `NumberFormatLocal` and other locale-dependent workbook behavior need separate review and scoped execution comparisons. Native-speaker review remains a release gate.

## Contributing translations

Edit `dashboard/locales.js` for browser interface text. Each catalog row contains `[original English message, French translation, German translation]`; the English message is its key. Keep `{placeholder}` names unchanged in each translation; the frontend fills them with values such as counts, labels and dates. Plural messages use `.one` and `.other` keys with an English entry in `translations.en` and French/German entries in the paired rows. Missing entries use the English text. Add a row when adding user-facing text, rather than translating workbook content or machine-readable status values.

Common server messages are translated in `dashboard/localization.py`. Built-in finding and report text follows the existing English/French/German entries in `data/rules.toml` and `src/`; custom TOML rules use the same three-language message convention. Keep the meaning of unknown coverage, conversion candidates, scoped comparisons and opt-in execution consistent across languages.

Run the browser/catalog and Python checks after editing translation behavior:

```sh
node --test tests/test_*.mjs
python -m unittest discover -s tests -p "test_*.py"
```

Check the affected screen in each language as well: longer labels must fit, form values must survive switching languages, and exported reports must keep the requested report language. Adding a fourth language requires coordinated scanner, report, rule, dashboard and API support; adding a catalog alone is insufficient.
