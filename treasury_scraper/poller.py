"""The treasury.gov poller -- the SECONDARY path.

Read config.py before changing the interval. Measured, not assumed:

    index   200  ttfb 9.21s / 10.25s / 9.22s
    leaf    200  ttfb 8.32s
    404     404  ttfb 38.39s
    conditional GET with If-None-Match -> 200, not 304

    Server-Timing: cdn-cache; desc=REVALIDATE, edge; dur=9021, origin; dur=4

The origin serves in 4 ms; Akamai adds nine seconds to every request and
ignores our validators, so there is no cheap poll and no 304 fast path. A
1 Hz loop would keep ten identical requests in flight, all returning the same
edge-stale HTML, and would be rate-limited within a minute.

So this poller is not the thing that gets you the trade -- the wire is. What
this gets you is the AUTHORITATIVE TEXT: the exact figures, the effective
date, the operation ceiling. On 08/19 the wire had the story at 08:36:18 and
the numbers by 08:38:40; the press release is what you check before sizing up.
"""

import random
import re
import time
import urllib.error
import urllib.request

from . import config, noise, state

# Akamai serves this page MINIFIED, with unquoted attribute values:
#
#   <a href=/news/press-releases/sb0611/ hreflang=en>
#
# A regex expecting href="..." matches nothing, warm() reports "0 slugs known"
# and the poller then fails OPEN -- it runs forever, never errors, and never
# alerts. That is the worst failure mode available here, so the quotes are
# optional and the trailing slash is tolerated.
_LINK = re.compile(r'href=["\']?(?:https://home\.treasury\.gov)?'
                   r'(/news/press-releases/([a-z]{2}\d{3,5}))/?["\'\s>]', re.I)
# NOT <h1>. On this template <h1> is the site logo ("U.S. Department of the
# Treasury") on every single page, so titling off it makes every release look
# identical and dedup collapses the whole feed into one item.
_TITLE = re.compile(r'<title[^>]*>(.*?)</title>', re.S | re.I)
_TITLE_SUFFIX = re.compile(r'\s*\|\s*U\.?S\.?\s*Department of the Treasury\s*$',
                           re.I)
# Anchored on uswds-page-title. Bare 'field--name-title' also matches nav
# blocks, and titling off the first hit named every release "About Treasury" --
# which then collapsed the entire feed into one L1 duplicate.
_PAGE_TITLE = re.compile(
    r'uswds-page-title[^>]*>.*?field--name-title[^>]*>(.*?)</span>',
    re.S | re.I)
# The article region. Without it the site NAV is part of the text, and the nav
# contains a "Readouts" menu link -- which made L2 drop every release on this
# site as a readout, silencing the poller completely while it reported healthy.
_BODY = re.compile(
    r'field--name-field-news-body(.*?)(?:</article>|<footer)', re.S | re.I)
_TAG = re.compile(r'<[^>]+>')
_SCRIPT = re.compile(r'<(script|style)\b.*?</\1>', re.S | re.I)


def _get(url, timeout=None):
    req = urllib.request.Request(url, headers={
        'User-Agent': config.USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout or config.HTTP_TIMEOUT_S) as r:
        return r.read().decode('utf-8', 'replace'), time.time() - t0


def _strip(html):
    return re.sub(r'\s+', ' ', _TAG.sub(' ', _SCRIPT.sub(' ', html))).strip()


def index_slugs(html):
    """Slugs on the index page, newest first.

    Slugs are sequential per Secretary (sb0242 was a Sept-2025 readout; sb0400
    exists, sb0450 does not). Sequential numbering makes NEXT-ID PROBING
    tempting -- fetch sb0451 before the index updates. Do not. A miss costs 38
    seconds and returns a WAF error page, so probing ahead is strictly slower
    than reading the index and far more likely to get the IP blocked.
    """
    out, seen = [], set()
    for path, slug in _LINK.findall(html):
        if slug not in seen:
            seen.add(slug)
            out.append((slug, 'https://home.treasury.gov' + path))
    return out


def parse_release(html, url='', dt=0.0):
    m = _TITLE.search(html) or _PAGE_TITLE.search(html)
    title = _TITLE_SUFFIX.sub('', _strip(m.group(1))) if m else ''
    b = _BODY.search(html)
    body = _strip(b.group(1)) if b else ''
    return {
        'source': 'GOV',
        'headline': title,
        'teaser': '',
        'body': body[:20000],
        'primary_instruments': [],
        'topics': [],
        'url': url,
        'fetch_seconds': dt,
        'body_found': bool(b),
    }


def fetch_release(url):
    html, dt = _get(url)
    return parse_release(html, url, dt)


class Poller:
    def __init__(self, on_alert=None, ledger=None, seen=None, verbose=True):
        self.on_alert = on_alert
        self.ledger = ledger or state.Ledger()
        self.seen = seen if seen is not None else state.SeenCache()
        self.verbose = verbose
        self.known = set()
        self.stop_requested = False
        self.stats = dict(polls=0, new=0, alerts=0, errors=0, http_seconds=0.0)

    def warm(self):
        """Record what is already published so the first poll does not alert
        on the entire back catalogue."""
        html, dt = _get(config.PRESS_INDEX)
        self.stats['http_seconds'] += dt
        self.known = {s for s, _ in index_slugs(html)}
        if not self.known:
            # Fail LOUD, not open. A parser that silently matches nothing looks
            # exactly like a quiet news day, forever.
            raise RuntimeError(
                'index parsed to 0 slugs from %d bytes -- the markup changed. '
                'Check _LINK against the raw HTML before trusting this poller.'
                % len(html))
        if self.verbose:
            print('[poller] warm: %d slugs known, index took %.1fs'
                  % (len(self.known), dt))
        return self.known

    def poll_once(self):
        self.stats['polls'] += 1
        try:
            html, dt = _get(config.PRESS_INDEX)
        except (urllib.error.URLError, OSError) as exc:
            self.stats['errors'] += 1
            if self.verbose:
                print('[poller] fetch failed: %s' % exc)
            return []
        self.stats['http_seconds'] += dt
        fresh = [(s, u) for s, u in index_slugs(html) if s not in self.known]
        results = []
        for slug, url in fresh:
            self.known.add(slug)
            self.stats['new'] += 1
            try:
                item = fetch_release(url)
                self.stats['http_seconds'] += item['fetch_seconds']
            except (urllib.error.URLError, OSError) as exc:
                self.stats['errors'] += 1
                if self.verbose:
                    print('[poller] leaf %s failed: %s' % (slug, exc))
                continue
            v = noise.classify(item, ledger=self.ledger, seen=self.seen,
                               hot=state.is_hot())
            results.append((item, v))
            if v.alert:
                self.stats['alerts'] += 1
                if self.on_alert:
                    self.on_alert(item, v)
                elif self.verbose:
                    print('\a[ALERT %.1f] %s\n         %s\n         %s'
                          % (v.score, item['headline'], ' '.join(v.reasons), url))
            elif self.verbose:
                print('[poller] %s %s -- %s' % (
                    slug, v.action, v.drop_reason or ' '.join(v.reasons)))
        return results

    def run(self):
        self.warm()
        while not self.stop_requested:
            self.poll_once()
            gap = state.poll_interval()
            # Jitter so we never form a detectable fixed-period signature at
            # the edge, and so a restart does not resynchronise onto it.
            time.sleep(max(1.0, gap + random.uniform(-config.POLL_JITTER_S,
                                                     config.POLL_JITTER_S)))
