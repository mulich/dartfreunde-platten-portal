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
    main.locks.clear()
    main.errors.clear()
    main.starting.clear()
    main.native_processes.clear()
    monkeypatch.setattr(main, 'automation_settings', {'hosts': ['rot', 'schwarz', 'blau']})
    monkeypatch.setattr(main, "DATA", tmp_path)
    page = SimpleNamespace(url="https://play.autodarts.com/", goto=AsyncMock(),
        screenshot=AsyncMock(return_value=b"test-image"),
        mouse=SimpleNamespace(click=AsyncMock(), move=AsyncMock(), wheel=AsyncMock()),
        keyboard=SimpleNamespace(insert_text=AsyncMock(), press=AsyncMock()))
    launch = AsyncMock(side_effect=lambda *a, **k: SimpleNamespace(pages=[page], close=AsyncMock()))
    runtime = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch), stop=AsyncMock())
    monkeypatch.setattr(main, "async_playwright", lambda: SimpleNamespace(start=AsyncMock(return_value=runtime)))
    with TestClient(main.app) as c:
        c.page = page
        c.launch = launch
        yield c


ORIGIN = {"origin": "http://testserver"}


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


def test_native_login_handoff(client, monkeypatch):
    monkeypatch.setattr(main, "native_chrome", lambda: "/test/chrome")
    process = SimpleNamespace(returncode=None)
    launch = AsyncMock(return_value=process)
    monkeypatch.setattr(main.asyncio, "create_subprocess_exec", launch)
    p = client.post("/api/players", json={"name": "Google-Spieler"}, headers=ORIGIN).json()
    base = f'/api/players/{p["id"]}'
    assert client.post(base + '/native-login', headers=ORIGIN).status_code == 200
    args = launch.call_args.args
    assert not any('automation' in a or 'remote-debugging' in a for a in args)
    assert '--disable-background-mode' in args
    assert str(main.DATA / 'profiles' / p['id']) in args[1]
    assert client.post(base + '/finish-login', headers=ORIGIN).status_code == 409
    assert client.delete(base, headers=ORIGIN).status_code == 409
    process.returncode = 0
    assert client.post(base + '/finish-login', headers=ORIGIN).status_code == 200
    assert client.launch.call_args.kwargs['channel'] == 'chrome'


def test_linux_chrome_requires_desktop(monkeypatch):
    monkeypatch.setattr(main.sys, 'platform', 'linux')
    monkeypatch.setattr(main.shutil, 'which', lambda name: '/usr/bin/google-chrome')
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    assert main.native_chrome() is None
    monkeypatch.setenv('WAYLAND_DISPLAY', 'wayland-0')
    assert main.native_chrome() == '/usr/bin/google-chrome'
    monkeypatch.delenv('WAYLAND_DISPLAY')
    monkeypatch.setenv('DISPLAY', ':0')
    assert main.native_chrome() == '/usr/bin/google-chrome'


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
