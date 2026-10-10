// SPDX-License-Identifier: EUPL-1.2
use crate::{
    lexer::{self, Kind, Token},
    model::{Finding, Module, UserForm, Verdict},
};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Rule {
    pub id: String,
    pub category: String,
    pub kind: String,
    pub pattern: Vec<String>,
    pub verdict: Verdict,
    pub hours: f64,
    pub messages: [String; 3],
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RuleFile {
    rules: Vec<Rule>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Weights {
    pub base_hours: f64,
    pub hours_per_code_line: f64,
    pub test_hours: f64,
    pub hours_per_userform: f64,
    pub hours_per_control_site: f64,
    pub control_site_cap: usize,
    pub occurrence_cap: usize,
    pub low_multiplier: f64,
    pub high_multiplier: f64,
}

impl Default for Weights {
    fn default() -> Self {
        Self {
            base_hours: 0.5,
            hours_per_code_line: 0.02,
            test_hours: 1.0,
            hours_per_userform: 2.0,
            hours_per_control_site: 0.1,
            control_site_cap: 50,
            occurrence_cap: 3,
            low_multiplier: 0.5,
            high_multiplier: 2.0,
        }
    }
}

impl Weights {
    pub fn load(path: Option<&Path>) -> Result<Self> {
        let weights: Self = match path {
            Some(p) => toml::from_str(
                &std::fs::read_to_string(p)
                    .with_context(|| format!("Reading weights {}", p.display()))?,
            )?,
            None => Self::default(),
        };
        ensure!(
            [
                weights.base_hours,
                weights.hours_per_code_line,
                weights.test_hours,
                weights.hours_per_userform,
                weights.hours_per_control_site,
                weights.low_multiplier,
                weights.high_multiplier
            ]
            .iter()
            .all(|v| v.is_finite() && *v >= 0.0),
            "Estimate weights must be finite and nonnegative"
        );
        ensure!(
            weights.occurrence_cap > 0
                && weights.control_site_cap > 0
                && weights.high_multiplier >= weights.low_multiplier,
            "Invalid estimate cap or range"
        );
        Ok(weights)
    }

    pub fn finding_hours(&self, findings: &[Finding]) -> f64 {
        let mut counts = BTreeMap::new();
        findings
            .iter()
            .map(|f| {
                let count = counts.entry(&f.rule_id).or_insert(0);
                *count += 1;
                if *count <= self.occurrence_cap {
                    f.hours
                } else {
                    0.0
                }
            })
            .sum()
    }

    pub fn userform_hours(&self, forms: &[UserForm]) -> f64 {
        forms
            .iter()
            .map(|form| {
                self.hours_per_userform
                    + form.controls.len().min(self.control_site_cap) as f64
                        * self.hours_per_control_site
            })
            .sum()
    }
}

pub fn load(path: Option<&Path>) -> Result<Vec<Rule>> {
    let mut rules: BTreeMap<String, Rule> =
        toml::from_str::<RuleFile>(include_str!("../data/rules.toml"))?
            .rules
            .into_iter()
            .map(|r| (r.id.clone(), r))
            .collect();
    if let Some(path) = path {
        let custom: RuleFile = toml::from_str(
            &std::fs::read_to_string(path)
                .with_context(|| format!("Reading rules {}", path.display()))?,
        )?;
        let mut seen = BTreeSet::new();
        for rule in custom.rules {
            ensure!(
                seen.insert(rule.id.clone()),
                "Duplicate custom rule ID: {}",
                rule.id
            );
            rules.insert(rule.id.clone(), rule);
        }
    }
    for rule in rules.values() {
        ensure!(
            !rule.id.is_empty()
                && !rule.pattern.is_empty()
                && rule.pattern.iter().all(|p| !p.is_empty()),
            "Empty rule ID or pattern"
        );
        ensure!(
            ["tokens", "com", "path", "reference", "feature"].contains(&rule.kind.as_str()),
            "Unsupported kind for {}",
            rule.id
        );
        ensure!(
            rule.hours.is_finite() && rule.hours >= 0.0,
            "Invalid hours for {}",
            rule.id
        );
        ensure!(
            rule.messages.iter().all(|m| !m.trim().is_empty()),
            "Missing translation for {}",
            rule.id
        );
    }
    Ok(rules.into_values().collect())
}

pub fn finding(rule: &Rule, line: Option<usize>) -> Finding {
    Finding {
        rule_id: rule.id.clone(),
        category: rule.category.clone(),
        line,
        verdict: rule.verdict,
        messages: rule.messages.clone(),
        hours: rule.hours,
    }
}

fn matches(rule: &Rule, tokens: &[Token], i: usize) -> bool {
    let token = &tokens[i];
    match rule.kind.as_str() {
        "tokens" => tokens.get(i..i + rule.pattern.len()).is_some_and(|window| {
            window.iter().zip(&rule.pattern).all(|(t, p)| {
                t.kind != Kind::String && t.kind != Kind::End && t.text.eq_ignore_ascii_case(p)
            })
        }),
        "com" => {
            token.kind == Kind::String
                && rule
                    .pattern
                    .iter()
                    .any(|p| token.text.to_lowercase().starts_with(&p.to_lowercase()))
                && tokens[..i].iter().rev().take(3).any(|t| {
                    t.kind == Kind::Identifier
                        && ["createobject", "getobject"].contains(&t.text.as_str())
                })
        }
        "path" => {
            token.kind == Kind::String
                && ((token.text.as_bytes().get(1) == Some(&b':')
                    && token.text.as_bytes().get(2) == Some(&b'\\'))
                    || token.text.starts_with("\\\\"))
        }
        _ => false,
    }
}

pub fn analyze(
    name: &str,
    kind: &str,
    source: String,
    rules: &[Rule],
    weights: &Weights,
) -> Module {
    let tokens = lexer::lex(&source);
    let normalized = source.replace("\r\n", "\n").replace('\r', "\n");
    let attributes: BTreeSet<_> = normalized
        .lines()
        .enumerate()
        .filter(|(_, line)| {
            line.trim_start()
                .to_ascii_lowercase()
                .starts_with("attribute ")
        })
        .map(|(i, _)| i + 1)
        .collect();
    let code_lines = tokens
        .iter()
        .filter(|t| t.kind != Kind::End && !attributes.contains(&t.line))
        .map(|t| t.line)
        .collect::<BTreeSet<_>>()
        .len();
    let mut findings = Vec::new();
    for rule in rules {
        let mut lines = BTreeSet::new();
        for i in 0..tokens.len() {
            if matches(rule, &tokens, i) && lines.insert(tokens[i].line) {
                findings.push(finding(rule, Some(tokens[i].line)));
            }
        }
    }
    let api_usage = crate::support::usage(&source);
    for call in api_usage.iter().filter(|call| !call.declared) {
        findings.push(Finding {
            rule_id: "MFLO001".into(), category: "object_model".into(), line: Some(call.line),
            verdict: Verdict::NeedsEdits, hours: 0.5,
            messages: [format!("{}.{} is not declared in the LibreOffice Excel VBA interface snapshot; review this call.", call.object_type, call.member), format!("{}.{} n’est pas déclaré dans l’interface VBA Excel de LibreOffice ; vérifier cet appel.", call.object_type, call.member), format!("{}.{} ist im LibreOffice-Excel-VBA-Schnittstellenstand nicht deklariert; Aufruf prüfen.", call.object_type, call.member)],
        });
    }
    findings.sort_by_key(|f| (f.line, f.rule_id.clone()));
    let verdict = if kind == "unknown" {
        Verdict::Unknown
    } else {
        findings
            .iter()
            .map(|f| f.verdict)
            .max()
            .unwrap_or(Verdict::NoKnownBlockers)
    };
    let trivial_document = kind == "document"
        && tokens
            .split(|token| token.kind == Kind::End)
            .all(|statement| {
                let mut words = statement
                    .iter()
                    .filter(|token| !attributes.contains(&token.line))
                    .map(|token| token.text.as_str());
                let mut first = words.next().unwrap_or("");
                while ["private", "public", "friend", "static"].contains(&first) {
                    first = words.next().unwrap_or("");
                }
                match first {
                    "" | "option" | "sub" | "function" | "property" => true,
                    "end" => matches!(words.next(), Some("sub" | "function" | "property")),
                    _ => false,
                }
            });
    let estimated_hours = if code_lines == 0 {
        0.0
    } else {
        code_lines as f64 * weights.hours_per_code_line
            + weights.finding_hours(&findings)
            + if trivial_document {
                0.0
            } else {
                weights.base_hours + weights.test_hours
            }
    };
    Module {
        name: name.into(),
        kind: kind.into(),
        lines: normalized.lines().count(),
        code_lines,
        normalized_sha256: lexer::fingerprint(&tokens, kind),
        verdict,
        estimated_hours,
        source: Some(source),
        findings,
        api_usage,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ignores_comments_and_unrelated_strings() {
        let rules = load(None).unwrap();
        assert_eq!(rules.len(), 60);
        let module = analyze("Test", "standard", "' Declare\nRem Shell\nMsgBox \"CreateObject Outlook.Application Shell\"\nDim myShell As String".into(), &rules, &Weights::default());
        assert!(module.findings.is_empty());
        let module = analyze("Test", "standard", "Declare PtrSafe Function X Lib \"kernel32\" () As Long\nSet o = CreateObject _\n (\"Outlook.Application\")\nShell \"calc.exe\"".into(), &rules, &Weights::default());
        assert!(
            module
                .findings
                .iter()
                .any(|f| f.rule_id == "MF001" && f.line == Some(1))
        );
        assert!(
            module
                .findings
                .iter()
                .any(|f| f.rule_id == "MF004" && f.line == Some(3))
        );
        assert_eq!(module.verdict, Verdict::NeedsRewrite);
    }
    #[test]
    fn caps_repeated_findings_in_estimate() {
        let weights = Weights::default();
        let rule = load(None).unwrap().remove(0);
        let findings = vec![finding(&rule, Some(1)); 10];
        assert_eq!(
            weights.finding_hours(&findings),
            rule.hours * weights.occurrence_cap as f64
        );
    }

    #[test]
    fn document_boilerplate_has_no_base_or_testing_overhead() {
        let rules = load(None).unwrap();
        let weights = Weights::default();
        for source in [
            "Attribute VB_Name = \"ThisWorkbook\"\n' Comment",
            "Option Explicit",
            "Option Explicit\nPrivate Sub Workbook_Open()\nEnd Sub",
            "Public Function Empty() As Long: End Function",
        ] {
            let module = analyze("ThisWorkbook", "document", source.into(), &rules, &weights);
            assert_eq!(
                module.estimated_hours,
                module.code_lines as f64 * weights.hours_per_code_line
                    + weights.finding_hours(&module.findings)
            );
        }
        for kind in ["document", "standard"] {
            let module = analyze(
                "Sheet1",
                kind,
                "Option Explicit\nPrivate Sub Worksheet_Activate()\nMsgBox 1\nEnd Sub".into(),
                &rules,
                &weights,
            );
            assert_eq!(
                module.estimated_hours,
                module.code_lines as f64 * weights.hours_per_code_line
                    + weights.finding_hours(&module.findings)
                    + weights.base_hours
                    + weights.test_hours
            );
        }
        let module = analyze(
            "Sheet1",
            "standard",
            "Option Explicit".into(),
            &rules,
            &weights,
        );
        assert!(module.estimated_hours >= weights.base_hours + weights.test_hours);
        let module = analyze(
            "Sheet1",
            "document",
            "Private Sub Test()\nShell \"cmd.exe\"\nEnd Sub".into(),
            &rules,
            &weights,
        );
        assert!(!module.findings.is_empty());
        assert!(module.estimated_hours > weights.base_hours + weights.test_hours);
    }

    #[test]
    fn userform_cost_scales_and_caps_sites_per_form() {
        use crate::model::FormControl;
        let weights = Weights::default();
        let control = FormControl {
            name: "Custom".into(),
            control_type: "CustomOrUnknown".into(),
            cached_index: 0,
        };
        let forms: Vec<_> = [0, 10, 80]
            .into_iter()
            .map(|count| UserForm {
                name: format!("Form{count}"),
                controls: vec![control.clone(); count],
                error: None,
                layout: None,
            })
            .collect();
        assert_eq!(weights.userform_hours(&[]), 0.0);
        assert_eq!(weights.userform_hours(&forms), 12.0);
        assert_eq!(forms[2].controls.len(), 80);
        assert_eq!(
            load(None)
                .unwrap()
                .iter()
                .find(|rule| rule.id == "MF050")
                .unwrap()
                .hours,
            0.0
        );
    }

    #[test]
    fn validates_custom_rules_and_weights() {
        let dir = tempfile::tempdir().unwrap();
        let rules_path = dir.path().join("rules.toml");
        let custom = include_str!("../data/rules.example.toml").replace("LOCAL001", "MF001");
        std::fs::write(&rules_path, &custom).unwrap();
        let rules = load(Some(&rules_path)).unwrap();
        assert_eq!(rules.len(), 60);
        let module = analyze(
            "Test",
            "standard",
            "LegacyClient.Connect".into(),
            &rules,
            &Weights::default(),
        );
        assert!(module.findings.iter().any(|f| f.rule_id == "MF001"));
        assert_eq!(module.verdict, Verdict::NeedsRewrite);
        std::fs::write(&rules_path, custom.replace("hours = 4", "hours = -1")).unwrap();
        assert!(load(Some(&rules_path)).is_err());
        let weights_path = dir.path().join("weights.toml");
        std::fs::write(&weights_path, "base_hours = -1").unwrap();
        assert!(Weights::load(Some(&weights_path)).is_err());
        for invalid in [
            "hours_per_userform = -1",
            "hours_per_control_site = nan",
            "control_site_cap = 0",
        ] {
            std::fs::write(&weights_path, invalid).unwrap();
            assert!(Weights::load(Some(&weights_path)).is_err());
        }
        std::fs::write(
            &weights_path,
            "base_hours = 5\nhours_per_code_line = 0\ntest_hours = 0",
        )
        .unwrap();
        let weights = Weights::load(Some(&weights_path)).unwrap();
        assert_eq!(weights.hours_per_userform, 2.0);
        assert_eq!(weights.hours_per_control_site, 0.1);
        assert_eq!(weights.control_site_cap, 50);
        assert_eq!(
            analyze(
                "Test",
                "standard",
                "MsgBox 1".into(),
                &load(None).unwrap(),
                &weights
            )
            .estimated_hours,
            5.0
        );
        assert_eq!(
            analyze("Unknown", "unknown", "MsgBox 1".into(), &rules, &weights).verdict,
            Verdict::Unknown
        );
    }
}
