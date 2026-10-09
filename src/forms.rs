// SPDX-License-Identifier: EUPL-1.2
//! MS-OFORMS site inventory; control values/layout remain in the original designer streams.
use crate::model::FormControl;
use anyhow::{Context, Result, bail, ensure};

struct Reader<'a> {
    bytes: &'a [u8],
    position: usize,
}
impl<'a> Reader<'a> {
    fn take(&mut self, size: usize) -> Result<&'a [u8]> {
        let end = self
            .position
            .checked_add(size)
            .context("Form length overflow")?;
        let value = self
            .bytes
            .get(self.position..end)
            .context("Truncated form record")?;
        self.position = end;
        Ok(value)
    }
    fn u16(&mut self) -> Result<u16> {
        Ok(u16::from_le_bytes(self.take(2)?.try_into()?))
    }
    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into()?))
    }
    fn align(&mut self, base: usize, size: usize) -> Result<()> {
        let pad = (size - (self.position - base) % size) % size;
        self.take(pad)?;
        Ok(())
    }
    fn picture(&mut self) -> Result<()> {
        ensure!(
            self.take(16)?
                == [
                    4, 0x52, 0xe3, 0x0b, 0x91, 0x8f, 0xce, 0x11, 0x9d, 0xe3, 0, 0xaa, 0, 0x4b,
                    0xb8, 0x51
                ],
            "Unknown form picture GUID"
        );
        ensure!(self.u32()? == 0x746c, "Invalid form picture header");
        let length = self.u32()? as usize;
        self.take(length)?;
        Ok(())
    }
    fn font(&mut self) -> Result<()> {
        let guid = self.take(16)?;
        if guid
            == [
                3, 0x52, 0xe3, 0x0b, 0x91, 0x8f, 0xce, 0x11, 0x9d, 0xe3, 0, 0xaa, 0, 0x4b, 0xb8,
                0x51,
            ]
        {
            ensure!(self.take(1)? == [1], "Invalid StdFont version");
            self.take(9)?;
            let length = self.take(1)?[0] as usize;
            self.take(length)?;
        } else if guid
            == [
                0x20, 9, 0xc2, 0xaf, 0x4e, 0xda, 0xce, 0x11, 0xb9, 0x43, 0, 0xaa, 0, 0x68, 0x87,
                0xb4,
            ]
        {
            ensure!(self.u16()? == 0x200, "Invalid TextProps version");
            let size = self.u16()? as usize;
            self.take(size)?;
        } else {
            bail!("Unknown form font GUID");
        }
        Ok(())
    }
}

pub fn controls(bytes: &[u8], code_page: u16) -> Result<Vec<FormControl>> {
    let mut r = Reader { bytes, position: 0 };
    ensure!(r.u16()? == 0x400, "Invalid FormControl version");
    let size = r.u16()? as usize;
    let mut block = Reader {
        bytes: r.take(size)?,
        position: 0,
    };
    let mask = block.u32()?;
    for bit in [1, 2, 3] {
        if mask & (1 << bit) != 0 {
            block.take(4)?;
        }
    }
    let flags = if mask & (1 << 6) != 0 {
        block.u32()?
    } else {
        0
    };
    if mask & (1 << 15) != 0 {
        r.picture()?;
    }
    if mask & (1 << 20) != 0 {
        r.font()?;
    }
    if mask & (1 << 21) != 0 {
        r.picture()?;
    }
    if flags & (1 << 15) == 0 {
        let classes = r.u16()?;
        ensure!(classes <= 1024, "Form class table limit exceeded");
        for _ in 0..classes {
            ensure!(r.u16()? == 0, "Invalid form class version");
            let size = r.u16()? as usize;
            r.take(size)?;
        }
    }
    let count = r.u32()? as usize;
    ensure!(count <= 10_000, "Form site limit exceeded");
    let length = r.u32()? as usize;
    let mut sites = Reader {
        bytes: r.take(length)?,
        position: 0,
    };
    let mut remaining = count;
    while remaining > 0 {
        let depth = sites.take(1)?[0];
        ensure!(depth <= 32, "Form nesting limit exceeded");
        let typ = sites.take(1)?[0];
        let n = if typ & 0x80 != 0 {
            ensure!(sites.take(1)? == [1], "Unsupported form site type");
            (typ & 0x7f) as usize
        } else {
            ensure!(typ == 1, "Invalid form depth/type");
            1
        };
        ensure!(n > 0 && n <= remaining, "Invalid form site count");
        remaining -= n;
    }
    sites.align(0, 4)?;
    let mut controls = Vec::new();
    for _ in 0..count {
        ensure!(sites.u16()? == 0, "Invalid OleSiteConcrete version");
        let size = sites.u16()? as usize;
        let mut site = Reader {
            bytes: sites.take(size)?,
            position: 0,
        };
        let mask = site.u32()?;
        let base = site.position;
        let mut name_length = 0;
        let mut index = 0x7fff;
        for bit in [0, 1, 2, 3, 4, 5, 6, 7, 9, 11, 12, 13, 14] {
            if mask & (1 << bit) == 0 {
                continue;
            }
            let width = if [6, 7, 9].contains(&bit) { 2 } else { 4 };
            site.align(base, width)?;
            if width == 2 {
                let value = site.u16()?;
                if bit == 7 {
                    index = value;
                }
            } else {
                let value = site.u32()?;
                if bit == 0 {
                    name_length = value;
                }
            }
        }
        site.align(base, 4)?;
        let name_data = site.take((name_length & 0x7fff_ffff) as usize)?;
        let name = crate::ovba::decode(
            name_data,
            if name_length & 0x8000_0000 != 0 {
                code_page
            } else {
                1200
            },
        )?;
        let control_type = match index {
            7 => "Form",
            12 => "Image",
            14 => "Frame",
            15 => "MorphData",
            16 => "SpinButton",
            17 => "CommandButton",
            18 => "TabStrip",
            21 => "Label",
            23 => "TextBox",
            24 => "ListBox",
            25 => "ComboBox",
            26 => "CheckBox",
            27 => "OptionButton",
            28 => "ToggleButton",
            47 => "ScrollBar",
            57 => "MultiPage",
            _ => "CustomOrUnknown",
        };
        controls.push(FormControl {
            name,
            control_type: control_type.into(),
            cached_index: index,
        });
    }
    Ok(controls)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn site_inventory_and_bounds() {
        let mut bytes = vec![0, 4, 8, 0, 0x40, 0, 0, 0, 0, 0x80, 0, 0];
        bytes.extend(1u32.to_le_bytes());
        let mut site = vec![0, 1, 0, 0, 0, 0, 8, 0, 0x80, 0, 0, 0];
        site.extend(17u16.to_le_bytes());
        site.extend([0, 0]);
        bytes.extend((site.len() as u32).to_le_bytes());
        bytes.extend(site);
        let result = controls(&bytes, 1252).unwrap();
        assert_eq!(result[0].control_type, "CommandButton");
        assert!(controls(&bytes[..bytes.len() - 1], 1252).is_err());
    }
}
