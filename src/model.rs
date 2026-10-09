// SPDX-License-Identifier: EUPL-1.2
use serde::{Deserialize, Serialize};

#[derive(Debug, Default, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Verdict {
    NoKnownBlockers,
    NeedsEdits,
    NeedsRewrite,
    #[default]
    Unknown,
}

impl Verdict {
    pub fn key(self) -> &'static str {
        match self {
            Self::NoKnownBlockers => "no_known_blockers",
            Self::NeedsEdits => "needs_edits",
            Self::NeedsRewrite => "needs_rewrite",
            Self::Unknown => "unknown",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    pub rule_id: String,
    pub category: String,
    pub line: Option<usize>,
    pub verdict: Verdict,
    pub messages: [String; 3],
    pub hours: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Module {
    pub name: String,
    pub kind: String,
    pub lines: usize,
    pub code_lines: usize,
    pub normalized_sha256: String,
    pub verdict: Verdict,
    pub estimated_hours: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
    pub findings: Vec<Finding>,
    #[serde(default)]
    pub api_usage: Vec<ApiUsage>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiUsage {
    pub object_type: String,
    pub member: String,
    pub line: usize,
    pub declared: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Query {
    pub name: String,
    pub sha256: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
    #[serde(default)]
    pub names: Vec<String>,
    #[serde(default)]
    pub steps: Vec<String>,
    #[serde(default)]
    pub sources: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FormControl {
    pub name: String,
    pub control_type: String,
    pub cached_index: u16,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserForm {
    pub name: String,
    pub controls: Vec<FormControl>,
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub layout: Option<String>,
}

#[derive(Debug, Default, Clone, Serialize, Deserialize)]
pub struct Workbook {
    pub path: String,
    pub size_bytes: u64,
    #[serde(default)]
    pub owner: Option<String>,
    pub modified_unix_seconds: Option<u64>,
    pub status: String,
    pub error: Option<String>,
    pub protected: Option<bool>,
    #[serde(default)]
    pub code_page: Option<u16>,
    #[serde(default)]
    pub entry_points: Vec<String>,
    #[serde(default)]
    pub macro_assignments: Vec<String>,
    #[serde(default)]
    pub forms: Vec<UserForm>,
    pub features: Vec<String>,
    pub references: Vec<String>,
    #[serde(default)]
    pub connections: Vec<String>,
    pub modules: Vec<Module>,
    pub queries: Vec<Query>,
    pub findings: Vec<Finding>,
    pub verdict: Verdict,
}

impl Workbook {
    pub fn refresh_verdict(&mut self) {
        self.verdict = if self.status == "inspected" {
            self.modules
                .iter()
                .map(|m| m.verdict)
                .chain(self.findings.iter().map(|f| f.verdict))
                .max()
                .unwrap_or(Verdict::NoKnownBlockers)
        } else {
            Verdict::Unknown
        };
    }

    pub fn remove_source(&mut self) {
        for module in &mut self.modules {
            module.source = None;
        }
        for query in &mut self.queries {
            query.source = None;
        }
        for form in &mut self.forms {
            form.layout = None;
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DuplicateMember {
    pub workbook: String,
    pub module: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DuplicateGroup {
    pub hash: String,
    pub members: Vec<DuplicateMember>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Scan {
    pub schema_version: String,
    pub tool_version: String,
    pub generated_unix_seconds: u64,
    pub language: String,
    pub source_included: bool,
    pub rules: Vec<crate::rules::Rule>,
    pub estimate: crate::rules::Weights,
    pub unique_modules: usize,
    pub estimated_hours_low: f64,
    pub estimated_hours_high: f64,
    pub discovery_errors: Vec<String>,
    pub duplicates: Vec<DuplicateGroup>,
    pub workbooks: Vec<Workbook>,
}
