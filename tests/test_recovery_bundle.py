import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest

spec = importlib.util.spec_from_file_location('recovery_bundle', Path(__file__).parents[1]/'tools/recovery_bundle.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def fixture(tmp_path, name='src/example.txt'):
    archive=tmp_path/'private.tar.gz'
    data=b'original deployment bytes\r\n'
    with tarfile.open(archive,'w:gz') as tar:
        member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o644
        tar.addfile(member,io.BytesIO(data))
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps([dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())]))
    return archive,manifest,data


def test_exact_archive_roundtrip_and_existing_destination_refused(tmp_path):
    archive,manifest,data=fixture(tmp_path)
    output=tmp_path/'stage'
    count,_=recovery.stage(output,archive,recovery.sha(archive),manifest)
    assert count==1 and (output/'src/example.txt').read_bytes()==data
    with pytest.raises(ValueError,match='OUTPUT_MUST_BE_NEW'):
        recovery.stage(output,archive,recovery.sha(archive),manifest)


@pytest.mark.parametrize('name',['../outside','/absolute','C:/outside','src/../../outside','src\\outside'])
def test_archive_paths_refused_before_any_output(tmp_path,name):
    archive,manifest,_=fixture(tmp_path,name)
    output=tmp_path/'stage'
    with pytest.raises(ValueError,match='UNSAFE_OR_UNEXPECTED'):
        recovery.stage(output,archive,recovery.sha(archive),manifest)
    assert not output.exists()


def test_changed_archive_and_manifest_refused(tmp_path):
    archive,manifest,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='PRIVATE_ARCHIVE_SHA'):
        recovery.stage(tmp_path/'stage',archive,'0'*64,manifest)
    rows=json.loads(manifest.read_text());rows[0]['sha256']='0'*64
    manifest.write_text(json.dumps(rows))
    with pytest.raises(ValueError,match='PRIVATE_FILE_SHA'):
        recovery.stage(tmp_path/'stage',archive,recovery.sha(archive),manifest)
    assert not (tmp_path/'stage').exists()
