"""Stable user storage, including migration out of MSIX virtualized AppData."""
from __future__ import annotations

from contextlib import contextmanager, closing
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3


class StorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class StorageResult:
    database_path: Path
    first_run: bool
    migrated: bool = False


def data_directory() -> Path:
    # USERPROFILE is identical inside and outside a packaged parent process.
    return Path(os.environ.get('USERPROFILE', str(Path.home()))) / 'Documents' / 'EnglishReadingMarker'


def _connect_readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)


def _inspect(path):
    with closing(_connect_readonly(path)) as db:
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise StorageError(f'数据库完整性检查失败：{path}')
        counts = {}
        for table in ('articles', 'annotations', 'vocabulary'):
            counts[table] = db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
        counts['sync'] = bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='sync_settings'").fetchone())
        return counts


def backup_database(source: Path, destination: Path | None = None) -> Path:
    source = Path(source)
    folder = source.parent / 'backups'
    destination = destination or folder / ('manual_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.sqlite3')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.partial')
    try:
        with closing(_connect_readonly(source)) as original, closing(sqlite3.connect(temporary)) as copy:
            original.backup(copy)
        _inspect(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _legacy_paths():
    profile = Path(os.environ.get('USERPROFILE', str(Path.home())))
    local = profile / 'AppData' / 'Local'
    roots = [Path(os.environ.get('LOCALAPPDATA', str(local))) / 'EnglishReadingMarker', local / 'EnglishReadingMarker']
    packages = local / 'Packages'
    if packages.exists():
        roots.extend(p / 'LocalCache/Local/EnglishReadingMarker' for p in packages.glob('OpenAI.Codex_*'))
    return [root / 'reader.sqlite3' for root in roots]


@contextmanager
def _migration_lock(folder):
    with open(folder / 'storage.lock', 'a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def _merge_extra_articles(destination, source):
    """Merge current secondary stores without changing the primary sync identity."""
    from src.repository import ReaderRepository
    repository = ReaderRepository(destination)
    try:
        with closing(_connect_readonly(source)) as old:
            old.row_factory = sqlite3.Row
            for article in old.execute('SELECT * FROM articles'):
                existing = repository.connection.execute('SELECT id FROM articles WHERE title=? AND text=?', (article['title'], article['text'])).fetchone()
                article_id = existing[0] if existing else repository.create_article(article['title'], article['text'])
                for mark in old.execute('SELECT * FROM annotations WHERE article_id=?', (article['id'],)):
                    repository.add_annotation(article_id, mark['start'], mark['end'], mark['word'])
                for word in old.execute('SELECT * FROM vocabulary WHERE article_id=?', (article['id'],)):
                    repository.add_vocabulary(article_id, word['start'], word['end'], word['word'], word['definition'])
    finally:
        repository.close()


def prepare_storage(folder: Path | None = None, *, legacy_candidates=None) -> StorageResult:
    folder = Path(folder) if folder is not None else data_directory()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with _migration_lock(folder):
            return _prepare_locked(folder, legacy_candidates)
    except (sqlite3.Error, OSError, ValueError) as error:
        raise StorageError(f'无法安全读取或迁移资料，原资料已保留。\n{error}') from error


def _prepare_locked(folder, legacy_candidates):
    database = folder / 'reader.sqlite3'
    backups = folder / 'backups'
    backups.mkdir(exist_ok=True)
    _apply_pending_restore(database)
    if database.exists():
        _inspect(database)  # Never replace a damaged existing library with sample data.
        daily = backups / ('daily_' + datetime.now().strftime('%Y%m%d') + '.sqlite3')
        if not daily.exists():
            backup_database(database, daily)
        return StorageResult(database, False)
    candidates, failures, seen = [], [], set()
    for candidate in (_legacy_paths() if legacy_candidates is None else legacy_candidates):
        path = Path(candidate).resolve()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        try:
            candidates.append((path, _inspect(path)))
        except (sqlite3.Error, StorageError) as error:
            failures.append(str(path))
    if failures:
        raise StorageError('发现无法读取的旧资料库，请先恢复备份；没有创建空资料库：\n' + '\n'.join(failures))
    if not candidates:
        return StorageResult(database, True)
    candidates.sort(key=lambda item: (item[1]['articles'], item[1]['annotations'] + item[1]['vocabulary'], item[1]['sync'], item[0].stat().st_mtime), reverse=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    snapshots = []
    for index, (source, counts) in enumerate(candidates):
        snapshot = backups / f'legacy_{stamp}_{index}.sqlite3'
        backup_database(source, snapshot)
        snapshots.append((snapshot, source, counts))
    staging = folder / 'migration.sqlite3'
    backup_database(snapshots[0][0], staging)
    try:
        for snapshot, _, _ in snapshots[1:]:
            _merge_extra_articles(staging, snapshot)
        _inspect(staging)
        # Keep settings and caches from the primary library, without overwriting.
        primary_folder = snapshots[0][1].parent
        for filename in ('audio.ini',):
            source = primary_folder / filename
            if source.exists() and not (folder / filename).exists():
                shutil.copy2(source, folder / filename)
        backup_database(staging, backups / f'recovered_{stamp}.sqlite3')
        report = {'created_at': stamp, 'sources': [{'path': str(source), 'snapshot': str(snapshot), **counts} for snapshot, source, counts in snapshots], 'result': _inspect(staging)}
        (folder / 'migration-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        staging.replace(database)
    finally:
        staging.unlink(missing_ok=True)
    return StorageResult(database, False, True)


def backup_details(path):
    details = _inspect(path)
    details['path'] = str(path)
    details['modified'] = datetime.fromtimestamp(Path(path).stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    with closing(_connect_readonly(path)) as db:
        details['titles'] = [row[0] for row in db.execute('SELECT title FROM articles ORDER BY id')]
        details['instance'] = _instance(db)
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='study_items'").fetchone():
            details['notes'] = db.execute("SELECT count(*) FROM study_items WHERE key LIKE 'note:%' AND value!='null'").fetchone()[0]
            details['reviews'] = db.execute("SELECT count(*) FROM study_items WHERE key LIKE 'review:%'").fetchone()[0]
        else:
            details.update(notes=0, reviews=0)
    return details


def _instance(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='sync_settings'").fetchone():
        return None
    row = db.execute("SELECT value FROM sync_settings WHERE key='instance'").fetchone()
    return row[0] if row else None


def schedule_restore(source, database):
    """Stage an explicit restore; startup applies it before opening the repository."""
    source, database = Path(source), Path(database)
    details = backup_details(source)
    with closing(_connect_readonly(database)) as current:
        if not details['instance'] or details['instance'] != _instance(current):
            raise StorageError('此备份不是当前同步资料库的备份，无法直接替换。原文件保持不变。')
    before = backup_database(database)
    backup_database(source, database.parent / 'pending-restore.sqlite3')
    return before


def _apply_pending_restore(database):
    pending = database.parent / 'pending-restore.sqlite3'
    if not pending.exists(): return
    _inspect(pending)
    if not database.exists(): raise StorageError('待恢复备份缺少当前资料库，已停止自动恢复。')
    with closing(_connect_readonly(database)) as current, closing(sqlite3.connect(pending)) as restored:
        if _instance(current) != _instance(restored):
            raise StorageError('待恢复备份身份不匹配，已保留所有文件并停止恢复。')
        # Keep active pairing credentials and acknowledged operation IDs so that
        # reconnecting phones cannot replay changes already rolled back on purpose.
        for table in ('sync_devices', 'sync_operations'):
            for row in current.execute(f'SELECT * FROM {table}'):
                restored.execute(f'INSERT OR IGNORE INTO {table} VALUES (?,?)', tuple(row))
        high = current.execute('SELECT COALESCE(MAX(seq),0) FROM sync_journal').fetchone()[0]
        high = max(high, restored.execute('SELECT COALESCE(MAX(seq),0) FROM sync_journal').fetchone()[0])
        restored.execute('INSERT INTO sync_journal(seq,kind) VALUES (?,?)', (high+1, 'restore'))
        restored.commit()
    backup_database(database)
    pending.replace(database)
