"""模拟三种协议，不调用真实模型或读取个人配置。"""
import asyncio
import json

import httpx
import pytest

import model_providers as providers


@pytest.mark.parametrize('provider,path,key,response', [
    ('openai', '/v1/chat/completions', 'Authorization', {'choices': [{'message': {'content': 'OK'}}]}),
    ('anthropic', '/v1/messages', 'x-api-key', {'content': [{'type': 'thinking'}, {'type': 'text', 'text': 'OK'}]}),
    ('ollama', '/api/generate', 'Authorization', {'response': 'OK'}),
])
def test_protocol_payload_and_response(monkeypatch, provider, path, key, response):
    original = httpx.AsyncClient
    def handle(request):
        assert request.url.path == path
        assert 'synthetic' in request.headers[key]
        body = json.loads(request.content)
        assert body['model'] == 'model'
        assert body['stream'] is False
        if provider == 'anthropic':
            assert body['max_tokens'] > 0
            assert request.headers['anthropic-version'] == '2023-06-01'
        if provider == 'ollama':
            assert body['prompt'] == 'hello'
            assert body['format'] == 'json'
        else:
            assert body['messages'][0]['content'] == 'hello'
        return httpx.Response(200, json=response)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    settings = providers.resolve(provider, {'model': 'model', 'api_key': 'synthetic'})
    assert asyncio.run(providers.complete(settings, 'hello')) == 'OK'


def test_ollama_discovery_and_legacy_url(monkeypatch):
    original = httpx.AsyncClient
    def handle(request):
        assert request.url.path == '/api/tags'
        return httpx.Response(200, json={'models': [{'name': 'local:8b'}, {'name': 'local:8b'}]})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    settings = providers.resolve('ollama', {'url': 'http://localhost:11434/api/generate/'})
    assert asyncio.run(providers.discover(settings)) == ['local:8b']


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'https://user:key@example.com', 'https://example.com?key=secret', 'http://', 'http://localhost:bad'])
def test_reject_credential_urls(url):
    with pytest.raises(ValueError):
        providers.normalize_url(url, 'openai')


def test_anthropic_pagination(monkeypatch):
    original = httpx.AsyncClient
    def handle(request):
        second = request.url.params.get('after_id') == 'first'
        return httpx.Response(200, json={'data': [{'id': 'second' if second else 'first'}],
                                        'has_more': not second, 'last_id': 'first'})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    assert asyncio.run(providers.discover(providers.resolve('anthropic', {'api_key': 'test'}))) == ['first', 'second']
