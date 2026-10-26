"""Course changes cannot receive or delete data using an obsolete AI response."""
import asyncio
import json

import httpx
import pytest

import app


@pytest.mark.parametrize('change', ['none', 'move', 'name', 'description'])
@pytest.mark.parametrize('empty', [False, True])
def test_course_snapshot_guards_writeback_and_cleanup(tmp_path, monkeypatch, change, empty):
    monkeypatch.setattr(app, 'DATA_FILE', tmp_path / 'words.json')
    for name in ('_new_enrichment_candidates', '_enrich_states', '_enriching_ids'):
        monkeypatch.setattr(app, name, {})
    monkeypatch.setattr(app, '_enrich_post_check', lambda *args: (True, ''))
    async def scenario():
        queue = asyncio.Queue()
        monkeypatch.setattr(app, '_enrich_queue', queue)
        monkeypatch.setattr(app, '_event_queue', asyncio.Queue())
        book = app.create_notebook({'name': 'Finance', 'description': 'Bonds and markets'})
        created = await app.create_word({'word': 'security', 'notebook_id': book['id']})
        wid = created['word']['id']
        async def generate(word, context=''):
            assert context == 'Finance: Bonds and markets'
            if change == 'move':
                app.update_word(wid, {'notebook_id': 'default'})
            elif change == 'name':
                app.update_notebook(book['id'], {'name': 'Law'})
            elif change == 'description':
                app.update_notebook(book['id'], {'description': 'Contract law'})
            return ('', '', '') if empty else ('/test/', 'n. 证券', 'A security is traded.')
        monkeypatch.setattr(app, 'enrich_word', generate)
        task = asyncio.create_task(app._enrich_worker())
        try:
            await asyncio.wait_for(queue.join(), 3)
            words = app.load_words()['words']
            if empty and change == 'none':
                assert not words
            else:
                assert len(words) == 1
                assert words[0]['definition'] == ('n. 证券' if change == 'none' else '')
            if change != 'none':
                assert app._enrich_states[wid]['status'] == 'failed'
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(scenario())


@pytest.mark.parametrize('provider', ['ollama', 'deepseek'])
def test_course_context_reaches_both_model_providers(monkeypatch, provider):
    real_client = httpx.AsyncClient
    seen = []
    def respond(request):
        payload = json.loads(request.content)
        prompt = payload['prompt'] if provider == 'ollama' else payload['messages'][0]['content']
        seen.append(prompt)
        result = json.dumps({'phonetic': '/test/', 'definition': 'n. 证券', 'example': 'A security is traded.'})
        return httpx.Response(200, json={'response': result} if provider == 'ollama' else {'choices': [{'message': {'content': result}}]})
    monkeypatch.setattr(app.config, 'get_provider', lambda: provider)
    monkeypatch.setattr(app.config, 'get_deepseek_config', lambda: {'api_key': 'synthetic', 'model': 'test'})
    monkeypatch.setattr(app.httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    result = asyncio.run(app.enrich_word('Security', 'Finance: Bonds and markets'))
    assert result[1] == 'n. 证券'
    assert 'Course context (use for sense and example selection): Finance: Bonds and markets' in seen[0]
