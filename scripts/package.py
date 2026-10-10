# SPDX-License-Identifier: EUPL-1.2
"""Create a deterministic full tool archive, dependency SBOM and SHA-256 manifest."""
import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]


def sbom():
    cargo=shutil.which('cargo') or str(Path.home()/'.cargo/bin/cargo.exe')
    metadata=json.loads(subprocess.check_output([cargo,'metadata','--locked','--format-version','1'],cwd=ROOT))
    packages={item['id']:item for item in metadata['packages']}
    references={key:'pkg:cargo/'+quote(item['name'],safe='')+'@'+quote(item['version'],safe='') for key,item in packages.items()}
    components=[]
    for key,item in sorted(packages.items(),key=lambda pair:references[pair[0]]):
        component={'type':'application' if item['name']=='cellwright' else 'library','bom-ref':references[key],'name':item['name'],'version':item['version'],'purl':references[key]}
        if item.get('license'):component['licenses']=[{'expression':item['license']}]
        components.append(component)
    assert len({item['bom-ref'] for item in components})==len(components)
    dependencies=sorted([{'ref':references[node['id']],'dependsOn':sorted(references[key] for key in node['dependencies'])} for node in metadata['resolve']['nodes']],key=lambda item:item['ref'])
    application=next(item for item in components if item['name']=='cellwright')
    return {'bomFormat':'CycloneDX','specVersion':'1.6','version':1,'metadata':{'component':application},'components':[item for item in components if item is not application],'dependencies':dependencies}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--platform',choices=['windows-x86_64','linux-x86_64'],required=True)
    parser.add_argument('--out',type=Path,default=ROOT/'dist')
    args=parser.parse_args()
    if not args.binary.is_file():raise FileNotFoundError(args.binary)
    args.out.mkdir(parents=True,exist_ok=True)
    name='cellwright-0.1.1-'+args.platform
    archive=args.out/(name+'.zip')
    files={}
    for directory in ('.cargo','migration','harness','dashboard','docs','data','LICENSES','third-party-licenses'):
        for path in (ROOT/directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:files[path.relative_to(ROOT).as_posix()]=path.read_bytes()
    for filename in ('README.md','SECURITY.md','LICENSE','THIRD_PARTY_NOTICES.md','Cargo.lock','Cargo.toml','rust-toolchain.toml','requirements.txt','Start Cellwright.cmd','start-cellwright.sh'):
        files[filename]=(ROOT/filename).read_bytes()
    files['cellwright.exe' if args.platform.startswith('windows') else 'cellwright']=args.binary.read_bytes()
    files['demo/formatting-button.xlsm']=(ROOT/'corpus/generated/formatting-button.xlsm').read_bytes()
    files['sbom.cdx.json']=(json.dumps(sbom(),sort_keys=True,indent=2)+'\n').encode()
    hashes={filename:hashlib.sha256(content).hexdigest() for filename,content in sorted(files.items())}
    files['build-manifest.json']=(json.dumps({'schema_version':'1','platform':args.platform,'signed':False,'sha256':hashes,'sbom_scope':'Cargo.lock dependencies, including build/dev and all target platforms; optional Python and LibreOffice are installed separately'},sort_keys=True,indent=2)+'\n').encode()
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as output:
        for filename,content in sorted(files.items()):
            entry=zipfile.ZipInfo(name+'/'+filename,date_time=(1980,1,1,0,0,0))
            entry.create_system=3
            entry.external_attr=(0o100755 if filename in ('cellwright','start-cellwright.sh') else 0o100644)<<16
            entry.compress_type=zipfile.ZIP_DEFLATED
            output.writestr(entry,content)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    with archive.with_suffix('.zip.sha256').open('x',encoding='ascii') as output:output.write(digest+'  '+archive.name+'\n')
    with zipfile.ZipFile(archive) as check:assert check.testzip() is None
    print(f'{archive}: {digest}')


if __name__=='__main__':main()
