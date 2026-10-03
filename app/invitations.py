"""Read current Autodarts React notifications; use the site's own join button.

The notification structure and lobby:invite type were verified against the public
Autodarts frontend on 2026-10-03. Unknown structures fail closed.
"""
import asyncio
import time
from urllib.parse import urlsplit

SCAN = r"""() => {
  const invites = new Map();
  document.querySelectorAll('[data-portal-invitation]').forEach(el => delete el.dataset.portalInvitation);
  let finished = null;
  const visible = el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
  for (const el of document.querySelectorAll('button, main, [role="main"]')) {
    const key = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
    let fiber = key ? el[key] : null;
    let notification = null;
    for (let depth=0; fiber && depth<80; depth++, fiber=fiber.return) {
      const props = fiber.memoizedProps;
      if (props?.value?.state && typeof props.value.state.finished === 'boolean')
        finished = props.value.state.finished;
      const n = props?.notification;
      if (n?.type === 'lobby:invite' && n.id && n.body?.user && n.body?.lobby?.id)
        notification = n;
    }
    if (el.tagName !== 'BUTTON' || !visible(el) || el.disabled || !notification) continue;
    const label = (el.textContent || '').trim();
    if (!/^(accept|join|annehmen|akzeptieren|beitreten)$/i.test(label)) continue;
    const n = notification;
    el.dataset.portalInvitation = n.id;
    if (!invites.has(n.id)) invites.set(n.id, {
      id: String(n.id), sender: String(n.body.user.name || ''),
      sender_id: String(n.body.user.id || ''), lobby_id: String(n.body.lobby.id)
    });
  }
  const match = /^\/(match|matches)(\/|$)/.test(location.pathname);
  const lobby = /^\/lobby(\/|$)/.test(location.pathname);
  return {invites: [...invites.values()], busy: lobby || (match && finished !== true)};
}"""


def sender_allowed(invite, hosts):
    allowed = {value.strip().casefold() for value in hosts if value.strip()}
    return any(str(invite.get(key, '')).strip().casefold() in allowed
               for key in ('sender', 'sender_id') if invite.get(key))


class AutoAcceptor:
    def __init__(self, contexts, registry, locks, settings):
        self.contexts, self.registry = contexts, registry
        self.locks, self.settings = locks, settings
        self.status = {}
        self.attempts = {}
        self.drawer_checked = {}

    def report(self, ident, message, **extra):
        self.status[ident] = {**self.status.get(ident, {}), 'message': message, **extra}

    async def tick(self, ident):
        item = self.registry.get(ident)
        if not item or not item.get('auto_accept'):
            self.drawer_checked.pop(ident, None)
            self.report(ident, 'Automatik aus')
            return
        hosts = self.settings.get('hosts', [])
        if not hosts:
            self.report(ident, 'Bitte Board-Accounts freigeben')
            return
        context = self.contexts.get(ident)
        if not context or not context.pages:
            self.report(ident, 'Sitzung ist pausiert')
            return
        page = context.pages[-1]
        if urlsplit(page.url).netloc != 'play.autodarts.com':
            self.report(ident, 'Wartet auf Autodarts-Anmeldung')
            return
        snapshot = await asyncio.wait_for(page.evaluate(SCAN), timeout=5)
        if snapshot['busy']:
            self.report(ident, 'In Lobby oder Match – wartet auf Abschluss')
            return
        if not snapshot['invites'] and self.drawer_checked.get(ident) != page.url:
            self.drawer_checked[ident] = page.url
            # Existing unread notifications may no longer have a toast. Open
            # the native drawer once after activation, never toggle it repeatedly.
            button = page.locator('button[aria-label]')
            for index in range(await button.count()):
                candidate = button.nth(index)
                label = (await candidate.get_attribute('aria-label') or '').casefold()
                if ('notification' in label or 'benachrichtigung' in label) and not any(
                    word in label for word in ('close', 'schließen', 'dismiss')):
                    if await candidate.is_visible() and await candidate.get_attribute('aria-expanded') != 'true':
                        await candidate.click(timeout=2000)
                    break
            self.report(ident, 'Wartet auf Lobby-Einladung')
            return
        if not snapshot['invites']:
            self.report(ident, 'Wartet auf Lobby-Einladung')
            return
        for invite in snapshot['invites']:
            if not sender_allowed(invite, hosts):
                self.report(ident, 'Einladung ignoriert: Absender nicht freigegeben', sender=invite['sender'])
                continue
            key = (ident, invite['id'])
            previous = self.attempts.get(key)
            if previous and (previous['done'] or previous['count'] >= 3 or time.monotonic() - previous['at'] < 30):
                continue
            attempt = {'at': time.monotonic(), 'count': previous['count'] + 1 if previous else 1, 'done': False}
            self.attempts[key] = attempt
            if len(self.attempts) > 512:
                self.attempts.pop(next(iter(self.attempts)))
            # Recheck config just before the write; disabling a player takes effect
            # even if an earlier scan was already in flight.
            if not item.get('auto_accept') or not sender_allowed(invite, self.settings.get('hosts', [])):
                return
            before = page.url
            buttons = page.locator('button[data-portal-invitation]')
            target = None
            for index in range(await buttons.count()):
                button = buttons.nth(index)
                if await button.get_attribute('data-portal-invitation') == invite['id'] and await button.is_visible():
                    target = button
                    break
            if target is None:
                continue
            self.report(ident, 'Nimmt Einladung an …', sender=invite['sender'])
            try:
                if not item.get('auto_accept') or not sender_allowed(invite, self.settings.get('hosts', [])):
                    return
                if (await asyncio.wait_for(page.evaluate(SCAN), timeout=5))['busy']:
                    return
                await target.click(timeout=3000)
                await page.wait_for_url(lambda url: (
                    urlsplit(str(url)).path == '/lobby/' + invite['lobby_id'] or
                    (str(url) != before and urlsplit(str(url)).path.startswith(('/match/', '/matches/')))
                ), timeout=6000)
                attempt['done'] = True
                self.report(ident, 'Lobby-Beitritt bestätigt', sender=invite['sender'],
                            last_accepted=time.time(), last_sender=invite['sender'], lobby_id=invite['lobby_id'])
            except Exception:
                self.report(ident, 'Beitritt nicht bestätigt – bitte Spieleransicht prüfen', sender=invite['sender'])
            # Only one invitation per player per cycle. The next cycle rechecks
            # match state before considering another host.
            return

    async def run(self):
        while True:
            async def check(ident):
                try:
                    async with self.locks.setdefault(ident, asyncio.Lock()):
                        await self.tick(ident)
                except Exception:
                    self.report(ident, 'Ansicht noch nicht bereit – wird erneut geprüft')
            await asyncio.gather(*(check(p['id']) for p in list(self.registry.items)))
            await asyncio.sleep(2)
