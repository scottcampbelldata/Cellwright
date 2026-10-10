// SPDX-License-Identifier: EUPL-1.2
//! Generate source-only VBA for controlled tests; contains no compiled macro cache.
use anyhow::Result;
use std::{
    io::{Cursor, Write},
    path::Path,
};

fn record(bytes: &mut Vec<u8>, id: u16, value: &[u8]) {
    bytes.extend(id.to_le_bytes());
    bytes.extend((value.len() as u32).to_le_bytes());
    bytes.extend(value);
}
fn wide(value: &str) -> Vec<u8> {
    value.encode_utf16().flat_map(u16::to_le_bytes).collect()
}
fn compressed(bytes: &[u8]) -> Vec<u8> {
    assert!(bytes.len() <= 3600);
    let mut body = Vec::new();
    for group in bytes.chunks(8) {
        body.push(0);
        body.extend(group);
    }
    let mut out = vec![1];
    out.extend((0xb000 | (body.len() as u16 - 1)).to_le_bytes());
    out.extend(body);
    out
}
fn main() -> Result<()> {
    let out = std::env::args().nth(1).expect("output .bin required");
    anyhow::ensure!(!Path::new(&out).exists(), "Output exists");
    let mut dir = Vec::new();
    record(&mut dir, 1, &3u32.to_le_bytes());
    record(&mut dir, 2, &0x409u32.to_le_bytes());
    record(&mut dir, 0x14, &0x409u32.to_le_bytes());
    record(&mut dir, 3, &1252u16.to_le_bytes());
    record(&mut dir, 4, b"Cellwright");
    for id in [5, 0x40, 6, 0x3d] {
        record(&mut dir, id, &[]);
    }
    record(&mut dir, 7, &0u32.to_le_bytes());
    record(&mut dir, 8, &0u32.to_le_bytes());
    record(&mut dir, 9, &1u32.to_le_bytes());
    dir.extend(0u16.to_le_bytes());
    record(&mut dir, 0xc, &[]);
    record(&mut dir, 0x3c, &[]);
    let mut original = zip::ZipArchive::new(std::fs::File::open("corpus/calamine-vba.xlsm")?)?;
    let mut data = Vec::new();
    std::io::Read::read_to_end(&mut original.by_name("xl/vbaProject.bin")?, &mut data)?;
    let mut template = cfb::CompoundFile::open(Cursor::new(data))?;
    let mut old_dir = Vec::new();
    std::io::Read::read_to_end(&mut template.open_stream("/VBA/dir")?, &mut old_dir)?;
    let old_dir = cellwright::ovba::decompress(&old_dir, 16 * 1024 * 1024)?;
    // Reuse only type-library records from the MIT-licensed calamine fixture.
    let reference_start = old_dir
        .windows(2)
        .position(|bytes| bytes == 0x16u16.to_le_bytes())
        .expect("references");
    let module_start = old_dir
        .windows(6)
        .position(|bytes| bytes == [0xf, 0, 2, 0, 0, 0])
        .expect("modules");
    dir.extend(&old_dir[reference_start..module_start]);
    record(&mut dir, 0xf, &3u16.to_le_bytes());
    record(&mut dir, 0x13, &0xffffu16.to_le_bytes());
    let arithmetic = format!(
        "Attribute VB_Name = \"Arithmetic\"\r\n{}",
        std::fs::read_to_string(
            std::env::args()
                .nth(2)
                .as_deref()
                .unwrap_or("corpus/Arithmetic.bas")
        )?
        .replace("\r\n", "\n")
        .replace('\n', "\r\n")
    );
    let this_workbook = "Attribute VB_Name = \"ThisWorkbook\"\r\nAttribute VB_Base = \"0{00020819-0000-0000-C000-000000000046}\"\r\nAttribute VB_PredeclaredId = True\r\nAttribute VB_Exposed = True\r\n";
    let this_workbook = format!(
        "{this_workbook}{}",
        match std::env::args().nth(3) {
            Some(path) => std::fs::read_to_string(path)?
                .replace("\r\n", "\n")
                .replace('\n', "\r\n"),
            None => String::new(),
        }
    );
    let sheet = "Attribute VB_Name = \"Sheet1\"\r\nAttribute VB_Base = \"0{00020820-0000-0000-C000-000000000046}\"\r\nAttribute VB_PredeclaredId = True\r\nAttribute VB_Exposed = True\r\n";
    let modules = [
        ("Arithmetic", arithmetic.as_str(), 0x21),
        ("ThisWorkbook", this_workbook.as_str(), 0x22),
        ("Sheet1", sheet, 0x22),
    ];
    for (name, _, typ) in &modules {
        record(&mut dir, 0x19, name.as_bytes());
        record(&mut dir, 0x47, &wide(name));
        record(&mut dir, 0x1a, name.as_bytes());
        record(&mut dir, 0x32, &wide(name));
        record(&mut dir, 0x1c, &[]);
        record(&mut dir, 0x48, &[]);
        record(&mut dir, 0x31, &0u32.to_le_bytes());
        record(&mut dir, 0x1e, &0u32.to_le_bytes());
        record(&mut dir, 0x2c, &0xffffu16.to_le_bytes());
        record(&mut dir, *typ, &[]);
        record(&mut dir, 0x2b, &[]);
    }
    record(&mut dir, 0x10, &[]);
    let mut cfb =
        cfb::CompoundFile::create_with_version(cfb::Version::V3, Cursor::new(Vec::new()))?;
    cfb.create_storage("/VBA")?;
    cfb.create_stream("/VBA/dir")?
        .write_all(&compressed(&dir))?;
    cfb.create_stream("/VBA/_VBA_PROJECT")?
        .write_all(&[0xcc, 0x61, 0xff, 0xff, 0, 0, 0])?;
    let project = "ID=\"{8A7F205E-71BA-4C25-B4AF-5CC6FB297504}\"\r\nDocument=ThisWorkbook/&H00000000\r\nDocument=Sheet1/&H00000000\r\nModule=Arithmetic\r\nName=\"Cellwright\"\r\nHelpContextID=\"0\"\r\nVersionCompatible32=\"393222000\"\r\n";
    cfb.create_stream("/PROJECT")?
        .write_all(project.as_bytes())?;
    for (name, source, _) in modules {
        cfb.create_stream(format!("/VBA/{name}"))?
            .write_all(&compressed(source.as_bytes()))?;
    }
    std::fs::write(out, cfb.into_inner().into_inner())?;
    Ok(())
}
