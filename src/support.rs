// SPDX-License-Identifier: EUPL-1.2
use crate::{
    lexer::{self, Kind},
    model::ApiUsage,
};
use serde_json::Value;
use std::{collections::BTreeMap, sync::LazyLock};

static TABLE: LazyLock<Value> = LazyLock::new(|| {
    serde_json::from_str(include_str!("../data/lo-vba-support.json"))
        .expect("validated compiled support table")
});

pub fn usage(source: &str) -> Vec<ApiUsage> {
    let tokens = lexer::lex(source);
    let mut types = BTreeMap::from([
        ("application".to_string(), "XApplication".to_string()),
        ("thisworkbook".into(), "XWorkbook".into()),
        ("activeworkbook".into(), "XWorkbook".into()),
        ("activesheet".into(), "XWorksheet".into()),
        ("worksheets".into(), "XWorksheet".into()),
        ("sheets".into(), "XWorksheet".into()),
        ("range".into(), "XRange".into()),
        ("cells".into(), "XRange".into()),
    ]);
    for statement in tokens.split(|token| token.kind == Kind::End) {
        if statement.first().is_some_and(|token| {
            ["dim", "static", "private", "public"].contains(&token.text.as_str())
        }) {
            for declaration in statement.windows(3) {
                if declaration[1].text == "as" {
                    let interface = match declaration[2].text.as_str() {
                        "range" => Some("XRange"),
                        "worksheet" => Some("XWorksheet"),
                        "workbook" => Some("XWorkbook"),
                        "application" => Some("XApplication"),
                        _ => None,
                    };
                    if let Some(interface) = interface {
                        types.insert(declaration[0].text.clone(), interface.into());
                    } else {
                        types.remove(&declaration[0].text);
                    }
                }
            }
        }
    }
    let mut out = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        if token.kind != Kind::Identifier || index > 0 && tokens[index - 1].text == "." {
            continue;
        }
        let Some(mut typ) = types.get(&token.text).cloned() else {
            continue;
        };
        let mut cursor = index + 1;
        loop {
            if tokens.get(cursor).is_some_and(|t| t.text == "(") {
                let mut nesting = 1;
                cursor += 1;
                while cursor < tokens.len() && nesting > 0 {
                    if tokens[cursor].kind == Kind::End {
                        break;
                    }
                    nesting += if tokens[cursor].text == "(" {
                        1
                    } else if tokens[cursor].text == ")" {
                        -1
                    } else {
                        0
                    };
                    cursor += 1;
                }
                if nesting != 0 {
                    break;
                }
            }
            if !tokens.get(cursor).is_some_and(|t| t.text == ".") {
                break;
            }
            let Some(member) = tokens
                .get(cursor + 1)
                .filter(|t| t.kind == Kind::Identifier)
            else {
                break;
            };
            let members = TABLE["interfaces"][&typ]["members"].as_array();
            let declaration = members.and_then(|members| {
                members.iter().find(|value| {
                    value["member"]
                        .as_str()
                        .is_some_and(|name| name.eq_ignore_ascii_case(&member.text))
                })
            });
            out.push(ApiUsage {
                object_type: typ.clone(),
                member: member.text.clone(),
                line: member.line,
                declared: declaration.is_some(),
            });
            let returns = declaration.and_then(|value| value["returns"].as_str());
            // IDL `any` carries no type information; stop rather than guessing a chained object's type.
            typ = match member.text.as_str() {
                "worksheets" | "sheets" => "XWorksheet".into(),
                "range" | "cells" => "XRange".into(),
                _ => match returns.filter(|name| name.starts_with('X')) {
                    Some(name) => name.into(),
                    None => break,
                },
            };
            cursor += 2;
        }
    }
    out.sort_by(|a, b| {
        (a.line, &a.object_type, &a.member).cmp(&(b.line, &b.object_type, &b.member))
    });
    out.dedup_by(|a, b| a.line == b.line && a.object_type == b.object_type && a.member == b.member);
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn typed_chains_and_unknown_members() {
        let calls = usage(
            "Dim r As Range\nr.Value = 1\nWorksheets(\"Data\").Range(\"A1\").DoesNotExist = 2\n' Range(\"A1\").Ignored\n",
        );
        assert!(
            calls.iter().any(|call| call.object_type == "XRange"
                && call.member == "value"
                && call.declared)
        );
        assert!(
            calls
                .iter()
                .any(|call| call.member == "range" && call.declared)
        );
        assert!(
            calls
                .iter()
                .any(|call| call.member == "doesnotexist" && !call.declared)
        );
        assert!(!calls.iter().any(|call| call.member == "ignored"));
    }
}
