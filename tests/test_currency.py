# -*- coding: utf-8 -*-
"""Currency, the sixth modifier axis — refuse on ambiguity, never on silence.

★★★ A SINGLE QUALIFIER IS NOT AMBIGUOUS. ADBE prints "record revenue of $6.76
billion ... 13% year-over-year growth, OR 12% IN CONSTANT CURRENCY". The
unqualified figure is REPORTED and the issuer says so by construction: the
"or" plus the qualifier MARKS THE EXCEPTION. Refusing there would discard a
value that may be the only one printed, and on ADBE it would refuse exactly
the reported figures the rows want.

★★ REFUSE ONLY WHEN BOTH ARE PRINTED AND THE ROW DECLARES NEITHER. ORCL prints
"between $1.83 and $1.91 in constant currency and between $1.85 and $1.93 in
USD" -- two legitimate midpoints, 1.87 and 1.89, identical in unit, period and
basis. No default is safe: the same release wants USD on its EPS guide and
CONSTANT CURRENCY on its cloud growth guide.

★ AND THE RANGE OWNS 'and'. The first cut used or/and/versus as contrast
markers, and "between $1.83 AND $1.91" cut the range in half -- masking USD
down to '$1.93' instead of '$1.85 and $1.93'. Which axis owns the token, asked
of the data: the range owns 'and', the contrast owns 'or'. The 'cc' token is
NOT wired at all: two characters against a six-character floor, n=0 in the
corpus.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X        # noqa: E402

ADBE = ('record revenue of $6.76 billion, representing 13% year-over-year '
        'growth, or 12% in constant currency')
ORCL = ('expected to be between $1.83 and $1.91 in constant currency and '
        'between $1.85 and $1.93 in USD')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def flat(t):
    return ' '.join((t or '').split())


def main():
    # ── one qualifier: resolve, do not refuse ────────────────────────────
    m, why = X.currency_mask(ADBE, {})
    check(m is not None and why is None,
          'a SINGLE qualifier does not refuse — the issuer marked the '
          'exception with "or"')
    m_rep, _ = X.currency_mask(ADBE, {'currencyBasis': 'REPORTED'})
    check('6.76' in m_rep and '13%' in m_rep and '12%' not in m_rep,
          'REPORTED keeps $6.76 and 13% and masks the 12% cc alternative')
    m_cc, _ = X.currency_mask(ADBE, {'currencyBasis': 'CONSTANT_CURRENCY'})
    check(flat(m_cc) == '12%',
          'CONSTANT_CURRENCY keeps only the qualified figure')
    _m, why_usd = X.currency_mask(ADBE, {'currencyBasis': 'USD'})
    check(_m is None and 'only as' in (why_usd or ''),
          'a row wanting USD where only cc is printed REFUSES, naming what '
          'the document does say')

    # ── both qualifiers, nothing declared: refuse, naming both ───────────
    m2, why2 = X.currency_mask(ORCL, {})
    check(m2 is None and 'CONSTANT_CURRENCY' in (why2 or '')
          and 'USD' in (why2 or ''),
          'BOTH printed and neither declared REFUSES, naming both printings')

    # ── the range owns 'and' ─────────────────────────────────────────────
    m_usd, _ = X.currency_mask(ORCL, {'currencyBasis': 'USD'})
    check('1.85' in m_usd and '1.93' in m_usd,
          "USD keeps the WHOLE range — 'and' belongs to the range, not to "
          'the contrast')
    check('1.83' not in m_usd and '1.91' not in m_usd,
          'and the constant-currency range is masked out of it')
    m_cc2, _ = X.currency_mask(ORCL, {'currencyBasis': 'CONSTANT_CURRENCY'})
    check('1.83' in m_cc2 and '1.91' in m_cc2 and '1.93' not in m_cc2,
          'and CONSTANT_CURRENCY keeps its own range only')

    # ── masking preserves every offset ───────────────────────────────────
    check(len(m_usd) == len(ORCL) and len(m_rep) == len(ADBE),
          'the mask is the SAME LENGTH as the window — offsets stay valid, '
          'because a frame moved by hand is what put header lookups on the '
          'dateline')

    # ── 'cc' is not a token ──────────────────────────────────────────────
    m3, why3 = X.currency_mask('revenue grew 12% cc', {})
    check(why3 is None,
          "bare 'cc' is NOT wired: two characters against a six-character "
          'floor, and n=0 in the corpus')

    # ── nothing qualified at all ─────────────────────────────────────────
    m4, why4 = X.currency_mask('revenue of $6.76 billion', {})
    check(why4 is None and m4 == 'revenue of $6.76 billion',
          'a release with no currency qualifier is untouched')
    check(X.currency_of(X.currency_spans(ADBE), 0) == 'REPORTED',
          'a position outside every qualified region reads as REPORTED')


main()
