# SPDX-License-Identifier: EUPL-1.2
"""Development-only snapshot of LibreOffice's declared Excel VBA interfaces."""
import concurrent.futures
import hashlib
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com/repos/LibreOffice/core"


def read(url):
    request = urllib.request.Request(url, headers={"User-Agent": "MacroFerry-support-generator"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main():
    commit = json.loads(read(API + "/commits/master"))["sha"]
    directory = "oovbaapi/ooo/vba/excel"
    files = json.loads(read(API + "/contents/" + directory + "?ref=" + commit))

    def extract(item):
        if not item["name"].endswith(".idl"):
            return None
        raw = read(item["download_url"])
        source = re.sub(r"/\*.*?\*/|//[^\n]*", "", raw.decode(), flags=re.S)
        declarations = []
        for attribute, typ, name, ending in re.findall(r"(?:\[([^\]]+)\]\s*)?([\w:]+(?:\s*<[^;]+?>)?)\s+(\w+)\s*([(;])", source):
            if "attribute" in attribute or ending == "(":
                declarations.append({"member": name, "returns": typ.split("::")[-1], "kind": "property" if "attribute" in attribute else "method"})
        return item["name"][:-4], {"members": declarations, "source_sha256": hashlib.sha256(raw).hexdigest(), "source": item["html_url"]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        interfaces = dict(result for result in pool.map(extract, files) if result)
    output = {"schema_version": "1", "libreoffice_commit": commit, "source": "https://github.com/LibreOffice/core/tree/" + commit + "/" + directory, "meaning": "IDL declaration only; execution parity requires a test case", "interfaces": interfaces, "tested": []}
    destination = ROOT / "data" / "lo-vba-support.json"
    destination.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert interfaces["XRange"]["members"]
    print(f"{len(interfaces)} IDL files, {sum(len(i['members']) for i in interfaces.values())} members: {destination}")


if __name__ == "__main__":
    main()
