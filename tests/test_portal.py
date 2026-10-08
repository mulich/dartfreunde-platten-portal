import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="dartkeller-test-")

import pytest
from fastapi.testclient import TestClient
from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    main.registry = main.Registry(tmp_path / "players.json")
    main.contexts.clear()
    main.account_identities.clear()
    main.locks.clear()
    main.errors.clear()
    main.starting.clear()
    monkeypatch.setattr(main, 'automation_settings', {'hosts': ['rot', 'schwarz', 'blau']})
    monkeypatch.setattr(main, "DATA", tmp_path)
    page = SimpleNamespace(url="https://play.autodarts.com/", goto=AsyncMock(),
        screenshot=AsyncMock(return_value=b"test-image"),
        mouse=SimpleNamespace(click=AsyncMock(), move=AsyncMock(), wheel=AsyncMock()),
        keyboard=SimpleNamespace(insert_text=AsyncMock(), press=AsyncMock()))
    launch = AsyncMock(side_effect=lambda *a, **k: SimpleNamespace(pages=[page], close=AsyncMock(), on=lambda *args: None))
    runtime = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch), stop=AsyncMock())
    monkeypatch.setattr(main, "async_playwright", lambda: SimpleNamespace(start=AsyncMock(return_value=runtime)))
    with TestClient(main.app) as c:
        c.page = page
        c.launch = launch
        yield c


ORIGIN = {"origin": "http://testserver"}


def test_emergency_recovery_only_targets_exact_accounts_and_is_idempotent(client):
    ids = []
    pages = []
    for name in ['Alias A', 'Alias B', 'Unrelated']:
        player = client.post('/api/players', json={'name':name}, headers=ORIGIN).json()
        main.registry.get(player['id'])['auto_accept'] = True
        ids.append(player['id'])
        page = SimpleNamespace(url='https://play.autodarts.com/lobby/old-lobby',
                               evaluate=AsyncMock(return_value={'busy':True,'invites':[]}))
        async def navigate(url, p=page, **kwargs):
            p.url = url
        page.goto = AsyncMock(side_effect=navigate)
        pages.append(page)
        main.contexts[player['id']] = SimpleNamespace(pages=[page], close=AsyncMock())
        main.account_identities[player['id']] = 'user-'+str(len(ids))
    payload = {'operation_id':'7f547e3b-86c4-47ca-9c9c-749527e691ee', 'board_account':'blau',
               'lobby_id':'old-lobby','user_ids':['user-1','user-2']}
    url = '/api/automation/lobby-recovery'
    assert client.post(url, json=payload, headers=ORIGIN).status_code == 200
    main.account_identities.clear()  # An acknowledged retry must not touch a new match/session.
    assert client.post(url, json=payload, headers=ORIGIN).status_code == 200
    for page in pages[:2]:
        page.goto.assert_awaited_once_with(main.AUTODARTS,wait_until='domcontentloaded',timeout=15000)
    pages[2].goto.assert_not_awaited()
    assert client.post(url,json={**payload,'user_ids':['user-3']},headers=ORIGIN).status_code == 409


def test_emergency_recovery_refuses_unknown_accounts_or_other_live_game(client):
    p = client.post('/api/players', json={'name':'A'}, headers=ORIGIN).json()
    main.registry.get(p['id'])['auto_accept'] = True
    page = SimpleNamespace(url='https://play.autodarts.com/matches/live-game',
        evaluate=AsyncMock(return_value={'busy':True,'invites':[]}),goto=AsyncMock())
    main.contexts[p['id']] = SimpleNamespace(pages=[page], close=AsyncMock())
    payload = {'operation_id':'7f547e3b-86c4-47ca-9c9c-749527e691ee','board_account':'blau',
               'lobby_id':'old-lobby','user_ids':['user-1']}
    assert client.post('/api/automation/lobby-recovery',json=payload,headers=ORIGIN).status_code == 409
    main.account_identities[p['id']] = 'user-1'
    assert client.post('/api/automation/lobby-recovery',json=payload,headers=ORIGIN).status_code == 409
    page.goto.assert_not_awaited()
    page.url = 'https://play.autodarts.com/matches/imported-completed-game'
    async def navigate(url, **kwargs):
        page.url = url
    page.goto.side_effect = navigate
    assert client.post('/api/automation/lobby-recovery',json={**payload,'completed_match_ids':['imported-completed-game']},headers=ORIGIN).status_code == 200


def test_direct_access_and_origin(client):
    assert client.get('/').status_code == 200
    assert client.get('/api/players').status_code == 200
    assert client.get('/login', follow_redirects=False).headers['location'] == '/'
    assert client.post('/api/players', json={'name': 'A'}, headers={'origin': 'http://evil.test'}).status_code == 403
    with pytest.raises(Exception):
        with client.websocket_connect('/ws/nope', headers={'origin': 'http://evil.test'}):
            pass


def test_isolated_profiles_and_persistence(client):
    a = client.post("/api/players", json={"name": "Anna"}, headers=ORIGIN).json()
    b = client.post("/api/players", json={"name": "Ben"}, headers=ORIGIN).json()
    for p in [a, b]:
        assert client.post(f'/api/players/{p["id"]}/start', headers=ORIGIN).status_code == 200
    paths = [call.args[0] for call in client.launch.call_args_list]
    assert len(set(paths)) == 2
    assert main.Registry(main.registry.path).items == [a, b]
    assert all(p["status"] == "running" for p in client.get("/api/players").json())
    assert client.post(f'/api/players/{a["id"]}/stop', headers=ORIGIN).status_code == 200
    assert b["id"] in main.contexts
    profile = main.DATA / "profiles" / a["id"]
    profile.mkdir(parents=True)
    (profile / "cookie").write_text("test")
    assert client.delete(f'/api/players/{a["id"]}', headers=ORIGIN).status_code == 200
    assert not profile.exists()
    assert main.registry.items == [b]


def test_screen_input(client):
    p = client.post("/api/players", json={"name": "Anna"}, headers=ORIGIN).json()
    client.post(f'/api/players/{p["id"]}/start', headers=ORIGIN)
    with client.websocket_connect(f'/ws/{p["id"]}', headers=ORIGIN) as ws:
        assert ws.receive_json()["type"] == "frame"
        ws.send_json({"type": "click", "x": 300, "y": 400})
        ws.send_json({"type": "text", "text": "Hallo"})
        ws.receive_json()
        client.page.mouse.click.assert_awaited_with(300.0, 400.0)
        client.page.keyboard.insert_text.assert_awaited_with("Hallo")


def test_validation(client):
    assert client.post("/api/players", json={"name": " "}, headers=ORIGIN).status_code == 400
    assert client.post("/api/players/unknown/start", headers=ORIGIN).status_code == 404


def test_legacy_desktop_profile_uses_fresh_chromium(client):
    item = {'id': 'legacy', 'name': 'Alt', 'browser': 'chrome'}
    main.registry.items.append(item)
    old = main.DATA / 'profiles' / 'legacy'
    old.mkdir(parents=True)
    (old / 'existing').write_text('preserved')
    assert client.post('/api/players/legacy/start', headers=ORIGIN).status_code == 200
    assert client.launch.call_args.args[0] == str(main.DATA / 'profiles/legacy-autodarts')
    assert 'channel' not in client.launch.call_args.kwargs
    assert (old / 'existing').read_text() == 'preserved'
    assert client.post('/api/players/legacy/native-login', headers=ORIGIN).status_code == 404


def test_automation_configuration(client):
    p = client.post('/api/players', json={'name': 'Anna'}, headers=ORIGIN).json()
    path = f'/api/players/{p["id"]}/auto-accept'
    assert client.get('/api/automation').json()['hosts'] == ['rot', 'schwarz', 'blau']
    assert client.put(path, json={'enabled': True}, headers=ORIGIN).status_code == 200
    assert main.Registry(main.registry.path).get(p['id'])['auto_accept'] is True
    assert client.put('/api/automation', json={'hosts': []}, headers=ORIGIN).status_code == 200
    assert client.put(path, json={'enabled': True}, headers=ORIGIN).status_code == 400
    assert client.put('/api/automation', json={'hosts': [' rot ', 'rot', 'blau']}, headers=ORIGIN).json()['hosts'] == ['rot', 'blau']
    assert (main.DATA / 'automation.json').exists()
    assert client.put(path, json={'enabled': False}, headers=ORIGIN).status_code == 200


def test_tournament_board_script_downloads(client):
    html = client.get('/').text
    boards = {'blau':'faa2cd5f-5d19-4e68-9749-1b7b95c753d4',
              'rot':'ad381dc0-7e86-45a1-9fa8-61c8b18ec89b',
              'schwarz':'6e390006-cdba-4ac5-b0bb-0e03eb880af6'}
    for name, ident in boards.items():
        url = f'/static/turnier-{name}.user.js'
        response = client.get(url)
        assert response.status_code == 200
        assert url in html
        assert ident in response.text
        assert 'https://turnier.mulich.de' in response.text
        assert f'https://dartportal.mulich.de{url}' in response.text


def test_shared_tournament_board_script_download(client):
    response=client.get('/static/turnier-board.user.js')
    assert response.status_code == 200
    assert 'function identifyBoard()' in response.text
    assert 'https://dartportal.mulich.de/static/turnier-board.user.js' in response.text
