// SPDX-License-Identifier: EUPL-1.2
use sha2::{Digest, Sha256};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Identifier,
    String,
    Number,
    Symbol,
    End,
}

#[derive(Debug, Clone)]
pub struct Token {
    pub text: String,
    pub kind: Kind,
    pub line: usize,
}

pub fn lex(source: &str) -> Vec<Token> {
    let chars: Vec<char> = source
        .replace("\r\n", "\n")
        .replace('\r', "\n")
        .chars()
        .collect();
    let mut out = Vec::new();
    let (mut i, mut line, mut statement_start) = (0, 1, true);
    while i < chars.len() {
        let ch = chars[i];
        if ch == '\n' || ch == ':' {
            out.push(Token {
                text: ";".into(),
                kind: Kind::End,
                line,
            });
            if ch == '\n' {
                line += 1;
            }
            statement_start = true;
            i += 1;
        } else if ch.is_whitespace() {
            i += 1;
        } else if ch == '\'' {
            while i < chars.len() && chars[i] != '\n' {
                i += 1;
            }
        } else if ch == '_'
            && chars[i + 1..]
                .iter()
                .take_while(|c| **c != '\n')
                .all(|c| c.is_whitespace())
        {
            while i < chars.len() && chars[i] != '\n' {
                i += 1;
            }
            if i < chars.len() {
                line += 1;
                i += 1;
            }
        } else if ch == '"' {
            let start_line = line;
            i += 1;
            let mut value = String::new();
            while i < chars.len() {
                if chars[i] == '"' {
                    i += 1;
                    if chars.get(i) != Some(&'"') {
                        break;
                    }
                }
                if chars[i] == '\n' {
                    line += 1;
                }
                value.push(chars[i]);
                i += 1;
            }
            out.push(Token {
                text: value,
                kind: Kind::String,
                line: start_line,
            });
            statement_start = false;
        } else if ch.is_alphabetic() || ch == '_' {
            let start = i;
            i += 1;
            while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '_') {
                i += 1;
            }
            let text: String = chars[start..i].iter().collect::<String>().to_lowercase();
            if (text == "rem"
                && !out
                    .last()
                    .is_some_and(|t: &Token| t.text == "." || t.text == "["))
                || (statement_start
                    && text == "attribute"
                    && chars[i..]
                        .iter()
                        .take(16)
                        .collect::<String>()
                        .trim_start()
                        .to_lowercase()
                        .starts_with("vb_name"))
            {
                while i < chars.len() && chars[i] != '\n' {
                    i += 1;
                }
                continue;
            }
            out.push(Token {
                text,
                kind: Kind::Identifier,
                line,
            });
            statement_start = false;
        } else {
            let kind = if ch.is_ascii_digit() {
                Kind::Number
            } else {
                Kind::Symbol
            };
            let start = i;
            i += 1;
            if kind == Kind::Number {
                while i < chars.len() && (chars[i].is_ascii_digit() || chars[i] == '.') {
                    i += 1;
                }
            }
            out.push(Token {
                text: chars[start..i].iter().collect(),
                kind,
                line,
            });
            statement_start = false;
        }
    }
    out
}

pub fn fingerprint(tokens: &[Token], kind: &str) -> String {
    let mut hash = Sha256::new();
    hash.update(kind.as_bytes());
    let mut last_end = true;
    for token in tokens {
        if token.kind == Kind::End && last_end {
            continue;
        }
        hash.update([token.kind as u8]);
        hash.update((token.text.len() as u64).to_le_bytes());
        hash.update(token.text.as_bytes());
        last_end = token.kind == Kind::End;
    }
    if !last_end {
        hash.update([Kind::End as u8]);
        hash.update(1_u64.to_le_bytes());
        hash.update(b";");
    }
    hash.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn comments_strings_and_continuations() {
        let tokens = lex(
            "' Shell\r\nRem Declare\nx = \"Shell \"\"Outlook\"\"\"\nCreateObject _\n (\"Outlook.Application\") ' comment",
        );
        let identifiers: Vec<_> = tokens
            .iter()
            .filter(|t| t.kind == Kind::Identifier)
            .map(|t| (t.text.as_str(), t.line))
            .collect();
        assert_eq!(identifiers, [("x", 3), ("createobject", 4)]);
        assert!(
            tokens
                .iter()
                .any(|t| t.text == "Shell \"Outlook\"" && t.kind == Kind::String)
        );
        assert!(
            !lex("10 Rem Shell\rMsgBox \"OK\"")
                .iter()
                .any(|t| t.text == "shell")
        );
        assert!(lex("obj.[Rem] = 1").iter().any(|t| t.text == "rem"));
    }
    #[test]
    fn duplicate_hash_preserves_strings_and_type() {
        let hash = |s| fingerprint(&lex(s), "standard");
        assert_eq!(
            hash("Attribute VB_Name = \"A\"\nSub Test()\nMsgBox \"Hello\"\nEnd Sub\n"),
            hash("' note\nsub test()\n  msgbox \"Hello\" ' note\nend sub")
        );
        assert_ne!(hash("MsgBox \"Hello\""), hash("MsgBox \"hello\""));
        assert_ne!(hash("foo bar"), hash("foobar"));
        assert_ne!(hash("x = 1"), fingerprint(&lex("x = 1"), "document"));
    }
}
