// SPDX-License-Identifier: EUPL-1.2
//! Bounded MS-OVBA decoding. Offsets and lengths are checked before every read.
use anyhow::{Context, Result, bail, ensure};

pub fn decompress(bytes: &[u8], limit: usize) -> Result<Vec<u8>> {
    ensure!(
        bytes.first() == Some(&1),
        "Invalid VBA compression signature"
    );
    let mut cursor = Reader(&bytes[1..]);
    let mut out = Vec::new();
    while !cursor.0.is_empty() {
        let header = cursor.u16()?;
        ensure!((header >> 12) & 7 == 3, "Invalid VBA chunk signature");
        let length = (header as usize & 0xfff) + 1;
        let chunk = cursor.take(length)?;
        let start = out.len();
        if header & 0x8000 == 0 {
            ensure!(length == 4096, "Invalid uncompressed VBA chunk length");
            ensure!(
                out.len() + length <= limit,
                "VBA decompression limit exceeded"
            );
            out.extend_from_slice(chunk);
        } else {
            let mut compressed = Reader(chunk);
            while !compressed.0.is_empty() {
                let flags = compressed.take(1)?[0];
                for bit in 0..8 {
                    if compressed.0.is_empty() {
                        break;
                    }
                    if flags & (1 << bit) == 0 {
                        ensure!(
                            out.len() - start < 4096 && out.len() < limit,
                            "VBA decompression limit exceeded"
                        );
                        out.push(compressed.take(1)?[0]);
                    } else {
                        let token = compressed.u16()? as usize;
                        let produced = out.len() - start;
                        let bits =
                            (usize::BITS - produced.saturating_sub(1).leading_zeros()).max(4);
                        let mask = 0xffff_usize >> bits;
                        let distance = (token >> (16 - bits)) + 1;
                        let count = (token & mask) + 3;
                        ensure!(distance <= produced, "VBA copy token points before chunk");
                        ensure!(
                            produced + count <= 4096 && out.len() + count <= limit,
                            "VBA decompression limit exceeded"
                        );
                        for _ in 0..count {
                            out.push(out[out.len() - distance]);
                        }
                    }
                }
            }
        }
    }
    Ok(out)
}

struct Reader<'a>(&'a [u8]);
impl<'a> Reader<'a> {
    fn take(&mut self, count: usize) -> Result<&'a [u8]> {
        let value = self.0.get(..count).context("Truncated VBA record")?;
        self.0 = &self.0[count..];
        Ok(value)
    }
    fn u16(&mut self) -> Result<u16> {
        Ok(u16::from_le_bytes(self.take(2)?.try_into()?))
    }
    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into()?))
    }
    fn variable(&mut self) -> Result<&'a [u8]> {
        let n = self.u32()? as usize;
        self.take(n)
    }
    fn record(&mut self, expected: u16) -> Result<&'a [u8]> {
        ensure!(
            self.u16()? == expected,
            "Unexpected VBA record; expected {expected:04x}"
        );
        self.variable()
    }
}

#[derive(Debug, Default)]
pub struct Module {
    pub name: String,
    pub stream: String,
    pub offset: usize,
    pub procedural: bool,
}
#[derive(Debug)]
pub struct Project {
    pub code_page: u16,
    pub references: Vec<String>,
    pub modules: Vec<Module>,
}

pub fn decode(bytes: &[u8], code_page: u16) -> Result<String> {
    let encoding =
        codepage::to_encoding_no_replacement(code_page).context("Unsupported VBA code page")?;
    let (text, errors) = encoding.decode_without_bom_handling(bytes);
    ensure!(!errors, "Invalid text for VBA code page {code_page}");
    Ok(text.into_owned())
}
fn unicode(bytes: &[u8]) -> Result<String> {
    ensure!(
        bytes.len().is_multiple_of(2),
        "Odd Unicode VBA record length"
    );
    decode(bytes, 1200)
}

pub fn parse_dir(bytes: &[u8]) -> Result<Project> {
    let mut r = Reader(bytes);
    let mut page = None;
    // Project records include paired MBCS/Unicode strings; PROJECTVERSION has a fixed six-byte payload.
    loop {
        let id = r.u16()?;
        if id == 0x16 || id == 0x33 || id == 0x2f || id == 0xd || id == 0xe || id == 0xf {
            r.0 = &bytes[bytes.len() - r.0.len() - 2..];
            break;
        }
        let size = r.u32()? as usize;
        let payload = r.take(if id == 9 { 6 } else { size })?;
        if id == 3 {
            ensure!(size == 2, "Invalid VBA code page record");
            page = Some(u16::from_le_bytes(payload.try_into()?));
        }
    }
    let code_page = page.context("Missing VBA code page")?;
    let mut references = Vec::new();
    let mut ref_name = String::new();
    let module_count;
    loop {
        let id = r.u16()?;
        match id {
            0xf => {
                ensure!(r.u32()? == 2, "Invalid VBA module count size");
                module_count = r.u16()? as usize;
                break;
            }
            0x16 => {
                ref_name = decode(r.variable()?, code_page)?;
                if r.0.starts_with(&0x3e_u16.to_le_bytes()) {
                    let text = unicode(r.record(0x3e)?)?;
                    if !text.is_empty() {
                        ref_name = text;
                    }
                }
            }
            0x33 => {
                let lib = decode(r.variable()?, code_page)?;
                references.push(format!("{ref_name}: {lib}"));
            }
            0xd | 0xe => {
                r.u32()?;
                let lib = decode(r.variable()?, code_page)?;
                references.push(format!("{ref_name}: {lib}"));
                if id == 0xe {
                    r.variable()?;
                }
                r.take(6)?;
                ref_name.clear();
            }
            0x2f => {
                r.u32()?;
                let lib = decode(r.variable()?, code_page)?;
                references.push(format!("{ref_name}: {lib}"));
                r.take(6)?;
                let next = r.u16()?;
                if next == 0x16 {
                    r.variable()?;
                    if r.0.starts_with(&0x3e_u16.to_le_bytes()) {
                        r.record(0x3e)?;
                    }
                    ensure!(r.u16()? == 0x30, "Invalid VBA extended control record");
                } else {
                    ensure!(next == 0x30, "Invalid VBA control record");
                }
                r.u32()?;
                let lib = decode(r.variable()?, code_page)?;
                references.push(format!("{ref_name}: {lib}"));
                r.take(26)?;
                ref_name.clear();
            }
            _ => bail!("Unsupported VBA reference record {id:04x}"),
        }
    }
    ensure!(module_count <= 10_000, "Too many VBA modules");
    r.record(0x13)?;
    let mut modules = Vec::new();
    for _ in 0..module_count {
        let mut module = Module {
            name: decode(r.record(0x19)?, code_page)?,
            ..Module::default()
        };
        let mut has_offset = false;
        loop {
            let id = r.u16()?;
            let value = r.variable()?;
            match id {
                0x47 => {
                    let text = unicode(value)?;
                    if !text.is_empty() {
                        module.name = text;
                    }
                }
                0x1a => module.stream = decode(value, code_page)?,
                0x32 => {
                    let text = unicode(value)?;
                    if !text.is_empty() {
                        module.stream = text;
                    }
                }
                0x31 => {
                    module.offset = u32::from_le_bytes(value.try_into()?) as usize;
                    has_offset = true;
                }
                0x21 => module.procedural = true,
                0x22 | 0x1c | 0x48 | 0x1e | 0x2c | 0x25 | 0x28 => (),
                0x2b => break,
                _ => bail!("Unsupported VBA module record {id:04x}"),
            }
        }
        ensure!(
            has_offset && !module.name.is_empty() && !module.stream.is_empty(),
            "Incomplete VBA module metadata"
        );
        ensure!(
            !module.stream.contains(['/', '\\']) && module.stream != "." && module.stream != "..",
            "Unsafe VBA stream name"
        );
        modules.push(module);
    }
    Ok(Project {
        code_page,
        references,
        modules,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn compressed_chunks_and_boundaries() {
        assert_eq!(
            decompress(&[1, 5, 0xb0, 8, b'a', b'b', b'c', 3, 0x20], 12).unwrap(),
            b"abcabcabc"
        );
        assert!(decompress(&[1, 5, 0xb0, 8, b'a', b'b', b'c', 3, 0], 8).is_err());
        assert!(decompress(&[1, 2, 0xb0, 1, 0, 0], 4096).is_err());
        assert!(decompress(&[1, 5, 0xb0, 0], 4096).is_err());
        assert!(parse_dir(&[0; 20]).is_err());
        assert_eq!(decode(&[0xc0], 1251).unwrap(), "А");
    }
}
