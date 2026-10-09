// SPDX-License-Identifier: EUPL-1.2
//! Lexical M inventory only; the optional Python converter parses supported query syntax.
#[derive(Default)]
pub struct Information {
    pub names: Vec<String>,
    pub steps: Vec<String>,
    pub sources: Vec<String>,
}
pub fn inspect(source: &str) -> Information {
    let chars: Vec<char> = source.chars().collect();
    let mut tokens = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        if chars[i..].starts_with(&['/', '/']) {
            while i < chars.len() && chars[i] != '\n' {
                i += 1;
            }
        } else if chars[i..].starts_with(&['/', '*']) {
            i += 2;
            let mut depth = 1;
            while i < chars.len() && depth > 0 {
                if chars[i..].starts_with(&['/', '*']) {
                    depth += 1;
                    i += 2;
                } else if chars[i..].starts_with(&['*', '/']) {
                    depth -= 1;
                    i += 2;
                } else {
                    i += 1;
                }
            }
        } else if chars[i] == '"' || chars[i..].starts_with(&['#', '"']) {
            let identifier = chars[i] == '#';
            i += if identifier { 2 } else { 1 };
            let mut value = String::new();
            while i < chars.len() {
                if chars[i] == '"' {
                    i += 1;
                    if chars.get(i) != Some(&'"') {
                        break;
                    }
                }
                value.push(chars[i]);
                i += 1;
            }
            tokens.push(if identifier { value } else { "<string>".into() });
        } else if chars[i].is_alphabetic() || chars[i] == '_' {
            let start = i;
            i += 1;
            while i < chars.len() && (chars[i].is_alphanumeric() || ['_', '.'].contains(&chars[i]))
            {
                i += 1;
            }
            tokens.push(chars[start..i].iter().collect());
        } else {
            if !chars[i].is_whitespace() {
                tokens.push(chars[i].to_string());
            }
            i += 1;
        }
    }
    let mut result = Information::default();
    for index in 0..tokens.len() {
        if tokens[index] == "shared" && tokens.get(index + 2).is_some_and(|value| value == "=") {
            result.names.push(tokens[index + 1].clone());
        }
        if tokens.get(index + 1).is_some_and(|value| value == "=")
            && index > 0
            && ["let", ","].contains(&tokens[index - 1].as_str())
        {
            result.steps.push(tokens[index].clone());
        }
        if tokens.get(index + 1).is_some_and(|value| value == "(")
            && [
                "File.",
                "Folder.",
                "Web.",
                "Sql.",
                "Odbc.",
                "OleDb.",
                "SharePoint.",
                "Excel.",
            ]
            .iter()
            .any(|prefix| tokens[index].starts_with(prefix))
        {
            result.sources.push(tokens[index].clone());
        }
    }
    result.sources.sort();
    result.sources.dedup();
    result
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ignores_comments_and_strings() {
        let info = inspect(
            "section S; shared #\"Sales query\" = let Source = File.Contents(\"sales.csv\"), Text = \"Web.Contents(\" /* Sql.Database() */ in Source;",
        );
        assert_eq!(info.names, ["Sales query"]);
        assert_eq!(info.sources, ["File.Contents"]);
    }
}
