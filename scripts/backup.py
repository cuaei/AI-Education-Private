"""Manual local backup. Stop the server first for a consistent files/database snapshot."""
import argparse
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path

def backup(data_dir,backup_dir):
    data=Path(data_dir).resolve();folder=Path(backup_dir).resolve();folder.mkdir(parents=True,exist_ok=True)
    if not (data/'training.sqlite').is_file():raise ValueError('找不到训练数据库。')
    target=folder/(time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns())+'.zip')
    with tempfile.TemporaryDirectory(dir=folder) as temporary:
        dbcopy=Path(temporary)/'training.sqlite'
        with closing(sqlite3.connect(data/'training.sqlite')) as source,closing(sqlite3.connect(dbcopy)) as dest:source.backup(dest)
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.write(dbcopy,'training.sqlite')
            for file in (data/'uploads').glob('*/*.csv'):archive.write(file,file.relative_to(data))
    for old in folder.glob('*.zip'):
        if old.stat().st_mtime<time.time()-7*86400:old.unlink()
    return target

def restore(source,destination):
    target=Path(destination).resolve()
    if target.exists():raise ValueError('恢复目录必须是尚不存在的新目录，避免覆盖现有记录。')
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            path=(target/item.filename).resolve()
            if not path.is_relative_to(target):raise ValueError('备份包含非法路径。')
        archive.extractall(target)
    return target

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['backup','restore']);parser.add_argument('--data-dir',default='runtime');parser.add_argument('--backup-dir',default='runtime/backups');parser.add_argument('--file');parser.add_argument('--destination')
    args=parser.parse_args()
    if args.action=='backup':print(backup(args.data_dir,args.backup_dir))
    elif args.file and args.destination:print(restore(args.file,args.destination))
    else:parser.error('restore 需要 --file 和 --destination 新目录。')
