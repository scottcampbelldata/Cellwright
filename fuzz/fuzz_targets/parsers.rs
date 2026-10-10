// SPDX-License-Identifier: EUPL-1.2
#![no_main]
use libfuzzer_sys::fuzz_target;
use std::io::{Cursor, Read};
fuzz_target!(|input: &[u8]| {
    if input.len()>1024*1024 {return;}
    let _=cellwright::ovba::decompress(input,1024*1024);
    let _=cellwright::ovba::parse_dir(input);
    let _=cellwright::forms::controls(input,1252);
    let _=cellwright::container::inspect_xml(input,&mut cellwright::model::Workbook::default());
    if let Ok(mut compound)=cfb::CompoundFile::open(Cursor::new(input)) {
        let entries:Vec<_>=compound.walk().take(100).filter(|entry|entry.is_stream()).map(|entry|entry.path().to_owned()).collect();
        for path in entries {if let Ok(stream)=compound.open_stream(path) {let mut bytes=Vec::new();let _=stream.take(1024*1024).read_to_end(&mut bytes);}}
    }
    if let Ok(mut archive)=zip::ZipArchive::new(Cursor::new(input)) {
        for index in 0..archive.len().min(100) {if let Ok(part)=archive.by_index(index) {let mut bytes=Vec::new();let _=part.take(1024*1024).read_to_end(&mut bytes);}}
    }
    if let Ok(source)=std::str::from_utf8(input) {let _=cellwright::lexer::lex(source);let _=cellwright::m_info::inspect(source);}
});
