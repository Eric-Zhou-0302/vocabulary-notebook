"""模型配置的持久化、密钥保护及供应商核验。"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import config
from app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / 'config.json'
    original = {'provider': 'deepseek', 'deepseek': {'api_key': 'private-test-key', 'model': 'old-model'},
                'ollama': {'url': 'http://localhost:11434/api/generate', 'model': 'local'},
                'srs': {'daily_new_limit': 17}}
    path.write_text(json.dumps(original))
    monkeypatch.setattr(config, 'CONFIG_FILE', path)
    monkeypatch.setattr(config, '_CONFIG', {})
    return TestClient(app)


def test_read_masks_key(client):
    response = client.get('/api/model-settings')
    assert response.status_code == 200
    assert 'private-test-key' not in response.text
    assert response.json()['deepseek']['api_key_configured'] is True


def test_save_preserves_key_and_other_settings(client):
    data = client.get('/api/model-settings').json()
    data['deepseek']['model'] = 'new-model'
    with patch('app.deepseek_models', AsyncMock(return_value=['new-model'])):
        response = client.put('/api/model-settings', json=data)
    assert response.status_code == 200
    assert 'private-test-key' not in response.text
    stored = json.loads(config.CONFIG_FILE.read_text())
    assert stored['deepseek']['api_key'] == 'private-test-key'
    assert stored['srs']['daily_new_limit'] == 17
    assert config.get_deepseek_config()['model'] == 'new-model'


def test_reject_removed_model_without_writing(client):
    before = config.CONFIG_FILE.read_text()
    with patch('app.deepseek_models', AsyncMock(return_value=['new-model'])):
        response = client.put('/api/model-settings', json=client.get('/api/model-settings').json())
        health = client.get('/api/health').json()
    assert response.status_code == 400
    assert config.CONFIG_FILE.read_text() == before
    assert health['status'] == 'model_unavailable'


def test_failed_discovery_does_not_report_expired(client):
    from fastapi import HTTPException
    with patch('app.deepseek_models', AsyncMock(side_effect=HTTPException(502, '无法核验'))):
        assert client.get('/api/health').json()['status'] == 'disconnected'
        assert client.post('/api/model-settings/deepseek-models', json={}).status_code == 502


def test_switch_to_ollama_and_reject_other_provider(client):
    data = client.get('/api/model-settings').json()
    data['provider'] = 'ollama'
    assert client.put('/api/model-settings', json=data).status_code == 200
    assert config.get_provider() == 'ollama'
    data['provider'] = 'other'
    assert client.put('/api/model-settings', json=data).status_code == 422
