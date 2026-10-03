import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.invitations import AutoAcceptor, sender_allowed


INVITE = {'id': 'notice-1', 'sender': 'Rot', 'sender_id': 'user-rot', 'lobby_id': 'lobby-1'}


class Buttons:
    def __init__(self, buttons):
        self.buttons = buttons

    async def count(self):
        return len(self.buttons)

    def nth(self, index):
        return self.buttons[index]


def setup(invites=None, busy=False, enabled=True, hosts=None):
    item = {'id': 'player', 'auto_accept': enabled}
    page = SimpleNamespace(url='https://play.autodarts.com/',
        evaluate=AsyncMock(return_value={'invites': invites if invites is not None else [INVITE], 'busy': busy}))
    async def clicked(**kwargs):
        page.url = 'https://play.autodarts.com/lobby/lobby-1'
    button = SimpleNamespace(get_attribute=AsyncMock(return_value='notice-1'),
        is_visible=AsyncMock(return_value=True), click=AsyncMock(side_effect=clicked))
    page.locator = lambda selector: Buttons([button] if 'data-portal-invitation' in selector else [])
    async def wait(predicate, **kwargs):
        if not predicate(page.url):
            raise TimeoutError()
    page.wait_for_url = AsyncMock(side_effect=wait)
    registry = SimpleNamespace(get=lambda ident: item)
    acceptor = AutoAcceptor({'player': SimpleNamespace(pages=[page])}, registry, {},
                            {'hosts': hosts if hosts is not None else ['rot', 'schwarz', 'blau']})
    return acceptor, page, button


def test_exact_sender_matching():
    assert sender_allowed(INVITE, ['rot'])
    assert sender_allowed(INVITE, ['user-rot'])
    assert not sender_allowed(INVITE, ['r'])
    assert not sender_allowed({**INVITE, 'sender': 'rot-fake'}, ['rot'])


def test_accept_and_confirm_once():
    acceptor, page, button = setup()
    async def check():
        await acceptor.tick('player')
        await acceptor.tick('player')
    asyncio.run(check())
    button.click.assert_awaited_once()
    assert acceptor.status['player']['last_sender'] == 'Rot'
    assert acceptor.status['player']['last_accepted'] > 0


def test_reject_unknown_busy_disabled_and_missing_hosts():
    for arguments in [{'invites': [{**INVITE, 'sender': 'fremd', 'sender_id': 'other'}]},
                      {'busy': True}, {'enabled': False}, {'hosts': []}]:
        acceptor, page, button = setup(**arguments)
        asyncio.run(acceptor.tick('player'))
        button.click.assert_not_awaited()


def test_unconfirmed_join_is_not_success_and_not_repeated_immediately():
    acceptor, page, button = setup()
    button.click.side_effect = None
    async def check():
        await acceptor.tick('player')
        await acceptor.tick('player')
    asyncio.run(check())
    button.click.assert_awaited_once()
    assert 'last_accepted' not in acceptor.status['player']
    assert 'nicht bestätigt' in acceptor.status['player']['message']


def test_login_page_and_paused_session_do_not_click():
    acceptor, page, button = setup()
    page.url = 'https://accounts.google.com/'
    asyncio.run(acceptor.tick('player'))
    button.click.assert_not_awaited()
    acceptor.contexts.clear()
    asyncio.run(acceptor.tick('player'))
    assert acceptor.status['player']['message'] == 'Sitzung ist pausiert'
