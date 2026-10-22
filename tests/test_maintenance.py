"""Exercise backup and lock behavior using disposable legacy and sync-format files."""
import asyncio
import json
from pathlib import Path

import pytest
import app
import instance_lock
import maintenance


def library(tmp_path, sync=False):
    data = tmp_path / '词库' / 'words.json'
    data.parent.mkdir()
    content = {'words': [{'id': 'test', 'word': 'Contract', 'definition': 'n. 合同', 'srs': {'reps': 3}}]}
    if sync:
        content.update(notebooks=[{'id': 'law'}], _sync={'operations': {'op': {'id': 'op'}}})
        content['words'][0]['review_history'] = [{'rating': 3}]
    data.write_text(json.dumps(content), encoding='utf8')
    config = tmp_path / 'config.json'
    config.write_text('{"private":"do-not-print"}', encoding='utf8')
    secrets = tmp_path / '.secrets'
    secrets.mkdir()
    (secrets / 'token.json').write_text('private-token', encoding='utf8')
    return data, config, secrets


@pytest.mark.parametrize('sync', [False, True])
def test_backup_verify_preserves_every_original_byte(tmp_path, sync):
    data, config, secrets = library(tmp_path, sync)
    original = {p: p.read_bytes() for p in [data, config, secrets/'token.json']}
    backup = maintenance.create_backup(data, config, secrets, tmp_path/'.backups', 'old-revision')
    summary = maintenance.verify_backup(backup)
    assert summary['words'] == summary['scheduled_words'] == 1
    assert summary['operations'] == (1 if sync else 0)
    assert summary['review_events'] == (1 if sync else 0)
    assert all(p.read_bytes() == value for p, value in original.items())
    manifest = json.loads((backup/'manifest.json').read_text(encoding='utf8'))
    assert manifest['revision'] == 'old-revision' and len(manifest['files']) == 3


@pytest.mark.parametrize('damage', ['copy', 'source', 'missing', 'traversal'])
def test_verification_stops_without_restoring_or_overwriting(tmp_path, damage):
    data, config, secrets = library(tmp_path)
    backup = maintenance.create_backup(data, config, secrets, tmp_path/'.backups')
    manifest = json.loads((backup/'manifest.json').read_text(encoding='utf8'))
    entry = next(item for item in manifest['files'] if Path(item['source']) == data.resolve())
    if damage == 'copy': (backup/entry['copy']).write_text('broken')
    if damage == 'source': data.write_text('{"words": []}')
    if damage == 'missing': data.unlink()
    if damage == 'traversal':
        entry['copy'] = '../outside'
        (backup/'manifest.json').write_text(json.dumps(manifest))
    before = data.read_bytes() if data.exists() else None
    with pytest.raises((RuntimeError, ValueError)):
        maintenance.verify_backup(backup)
    assert (data.read_bytes() if data.exists() else None) == before


def test_active_cache_blocks_backup_and_verification(tmp_path):
    data, config, secrets = library(tmp_path)
    backup = maintenance.create_backup(data, config, secrets, tmp_path/'.backups')
    with instance_lock.acquire(data):
        with pytest.raises(RuntimeError):
            maintenance.create_backup(data, config, secrets, tmp_path/'.backups')
        with pytest.raises(RuntimeError):
            maintenance.verify_backup(backup)
    maintenance.verify_backup(backup)


def test_startup_failure_releases_library_lock(tmp_path, monkeypatch):
    data, _, _ = library(tmp_path)
    monkeypatch.setattr(app, 'DATA_FILE', data)
    def invalid(): raise RuntimeError('invalid provider')
    monkeypatch.setattr(app.config, 'get_provider', invalid)
    async def scenario():
        with pytest.raises(RuntimeError, match='invalid provider'):
            async with app.lifespan(app.app):
                pytest.fail('Must reject invalid configuration')
    asyncio.run(scenario())
    with instance_lock.acquire(data): pass


def test_invalid_library_refuses_backup_without_mutating_it(tmp_path):
    data, config, secrets = library(tmp_path)
    data.write_text('damaged-json')
    with pytest.raises(ValueError):
        maintenance.create_backup(data, config, secrets, tmp_path/'.backups')
    assert data.read_text() == 'damaged-json'
    assert not (tmp_path/'.backups').exists()


def test_lifespan_error_stops_workers_before_releasing_cache(tmp_path, monkeypatch):
    data, _, _ = library(tmp_path)
    monkeypatch.setattr(app, 'DATA_FILE', data)
    monkeypatch.setattr(app.config, 'get_provider', lambda: 'deepseek')
    monkeypatch.setattr(app.config, 'get_sync_config', lambda: {'mode': 'disabled'})
    stopped = []
    async def worker():
        try:
            await asyncio.sleep(100)
        finally:
            with pytest.raises(RuntimeError):
                instance_lock.acquire(data)
            stopped.append(True)
    monkeypatch.setattr(app, '_enrich_worker', worker)
    monkeypatch.setattr(app, '_periodic_backup_loop', worker)
    monkeypatch.setattr(app, '_cloud_sync_loop', worker)
    async def scenario():
        with pytest.raises(ValueError, match='test failure'):
            async with app.lifespan(app.app):
                await asyncio.sleep(0)
                raise ValueError('test failure')
        assert len(stopped) == 3
    asyncio.run(scenario())
    with instance_lock.acquire(data): pass
