// SPDX-License-Identifier: EUPL-1.2
use std::{fs::Metadata, path::Path};

#[cfg(windows)]
pub fn owner(path: &Path, _metadata: &Metadata) -> Option<String> {
    use std::{os::windows::ffi::OsStrExt, ptr};
    use windows_sys::Win32::{
        Foundation::LocalFree,
        Security::{
            Authorization::{ConvertSidToStringSidW, GetNamedSecurityInfoW, SE_FILE_OBJECT},
            OWNER_SECURITY_INFORMATION,
        },
    };
    let name: Vec<u16> = path.as_os_str().encode_wide().chain([0]).collect();
    let (mut sid, mut descriptor, mut text) = (ptr::null_mut(), ptr::null_mut(), ptr::null_mut());
    // Windows owns both allocations; SID text avoids domain/account lookups during an offline scan.
    unsafe {
        if GetNamedSecurityInfoW(
            name.as_ptr(),
            SE_FILE_OBJECT,
            OWNER_SECURITY_INFORMATION,
            &mut sid,
            ptr::null_mut(),
            ptr::null_mut(),
            ptr::null_mut(),
            &mut descriptor,
        ) != 0
        {
            return None;
        }
        let result = if ConvertSidToStringSidW(sid, &mut text) != 0 {
            let mut chars = Vec::new();
            for i in 0..184 {
                let ch = *text.add(i);
                if ch == 0 {
                    break;
                }
                chars.push(ch);
            }
            let result = String::from_utf16(&chars).ok();
            LocalFree(text.cast());
            result
        } else {
            None
        };
        LocalFree(descriptor);
        result
    }
}
#[cfg(unix)]
pub fn owner(_path: &Path, metadata: &Metadata) -> Option<String> {
    use std::os::unix::fs::MetadataExt;
    Some(format!("uid:{}", metadata.uid()))
}
#[cfg(not(any(unix, windows)))]
pub fn owner(_path: &Path, _metadata: &Metadata) -> Option<String> {
    None
}
