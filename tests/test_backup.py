from scripts.backup import backup,restore
from backend.storage import Store
import pytest

def test_manual_backup_restores_to_new_directory_without_overwriting(tmp_path):
    source=tmp_path/'original';store=Store(source/'training.sqlite');store.create_user('learner','Password123!')
    folder=source/'uploads'/'test';folder.mkdir(parents=True);(folder/'v1.csv').write_text('sample')
    archive=backup(source,tmp_path/'backups');destination=restore(archive,tmp_path/'restored')
    assert Store(destination/'training.sqlite').find_user('learner')['username']=='learner'
    assert (destination/'uploads'/'test'/'v1.csv').read_text()=='sample'
    with pytest.raises(ValueError):restore(archive,destination)
