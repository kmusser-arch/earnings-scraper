"""Configuration. Read once at startup; never touched on the hot path."""

import os

# -- L0: SOURCE TRIAGE --------------------------------------------------------
# Measured over the 37,760-message capture in news.log (2026-08-19):
#
#   EDG  15,291  SEC filings          -- 40% of the wire, zero macro value
#   DJN  12,976  Dow Jones            -- 34%, and on 08/19 it was 32 min LATE
#   ---------------------------------------------------------------
#   HAM     609  Hammerstone squawk   -- had it FIRST, at 08:36:18
#   FLY     795  Fly on the Wall
#   SIN     772  Street Insider
#
# The three fast desks are 2,176 messages -- 5.8% of the wire. Alerting on them
# alone removes 94% of the volume and LOSES NOTHING: they led every other
# source on the founding case. DJN/BBG/WSJ stay subscribed as CONFIRMERS (L9)
# but never raise an alert of their own.
FAST_SOURCES = ['HAM', 'FLY', 'SIN']
CONFIRM_SOURCES = ['DJN', 'BBG', 'MKT', 'WSJ', 'FTI', 'RTN', 'BRR']
NEVER_ALERT = ['EDG', 'PCR', 'ADD', 'UNDF']

SUBSCRIBE_SOURCES = FAST_SOURCES + CONFIRM_SOURCES
DEFAULT_MODE = 'full'        # headlines mode carries no body -- see listener.py

# -- L3: VOCABULARY TIERS -----------------------------------------------------
# TIER_A fires the popup. These are the Office of Debt Management levers --
# supply, buybacks, the bill/coupon mix, the debt limit. They move the long end
# directly and the equity index through the discount rate.
TIER_A = [
    'liquidity support', 'buyback', 'buy-back', 'repurchase operation',
    'quarterly refunding', 'refunding', 'auction size', 'auction sizes',
    'nominal coupon', 'long-end', 'longer-dated', 'coupon issuance',
    'debt limit', 'extraordinary measures', 'financing estimates',
    'marketable borrowing', 'cash balance', 'bill supply', 'tga',
    'qra', 'debt management', 'issuance guidance',
]

# TIER_B logs and soft-alerts. Real, but second-order or slower-burning.
# NOTE: 'bessent' and 'treasury secretary' were here and have been removed.
# They are NAMES, not events -- every single treasury.gov release carries
# "Secretary of the Treasury Scott Bessent" in its boilerplate, so on the GOV
# path they matched 8 of 8 releases and discriminated nothing. Real Bessent
# news arrives carrying a Tier-A term of its own.
TIER_B = [
    'tariff', 'currency manipulat', 'exchange rate report', 'fx report',
    'sanction', 'sovereign', 'capital control', 'yield curve control',
]

# ACRONYMS must match case-SENSITIVELY and on a word boundary. Left lowercase
# and unbounded, 'tga' matches inside "mor-TGA-ge" and every MBA mortgage
# survey in the feed scores Tier-A. That single substring produced 20 of the
# first 32 alerts on the first replay.
ACRONYMS = {'tga', 'qra', 'tips'}

# TIER_Z is a HARD DROP even when a Tier-A word also appears. These are the
# ceremonial and personnel releases -- the bulk of treasury.gov by count --
# plus the two boilerplate classes that dominate the fast desks.
TIER_Z = [
    # treasury.gov ceremonial / personnel
    'readout', 'remarks by', 'remarks from', 'remarks as prepared',
    'statement from', 'chair’s statement', "chair's statement",
    'appoints', 'nominates', 'designates', 'welcomes', 'anniversary',
    'passing of', 'fact sheet on', 'travel to', 'bilateral meeting',
    'roundtable', 'op-ed', 'testimony',
    # ratings-agency traffic. Fitch/KBRA/Moody's assign ratings all day and
    # every one of them mentions debt. None of them move the long end.
    'assigns final ratings', 'assigns preliminary ratings',
    'assigns definitive ratings', 'assigns provisional ratings',
    'assigns aaa', 'rating action', 'affirms rating', 'affirms ratings',
    'places on watch', 'outlook revised to', 'kbra assigns', 'fitch assigns',
    'moody', 'downgrades to', 'upgrades to',
    # sell-side boilerplate on FLY / SIN
    'price target', 'pt lowered', 'pt raised', 'initiates coverage',
    'reiterates', 'resumes coverage', 'maintain outperform',
    # desk boilerplate on HAM
    'economic calendar', 'pivot levels', 'premarket movers', 'movers:',
    'earnings calendar', 'support (s)', 'resistance (r)',
]

# -- L5: THE BUYBACK HOMONYM --------------------------------------------------
# "buyback" is overwhelmingly a CORPORATE word. In the same 45-minute window as
# the founding case the wire carried SK Hynix ($29B), Curtiss-Wright ($100M),
# John Marshall Bancorp and Ipsos -- all share repurchases, all noise.
#
# A buyback headline is macro only if it also carries a sovereign-debt word.
SOVEREIGN_CONTEXT = [
    'treasury', 'u.s. debt', 'government debt', 'coupon', 'nominal',
    'long-end', 'longer-dated', 'bond market', 'sovereign', 'tips',
    'off-the-run', 'debt management', 'fiscal agent',
]
CORPORATE_TELLS = [
    'share buyback', 'share repurchase', 'stock buyback', 'own shares',
    'buyback program', 'buyback programme', 'repurchase program',
    'treasury shares', 'treasury stock', 'per share', 'authorized a',
]

# -- L6: INSTRUMENT / TOPIC ROUTING -------------------------------------------
# Free, professionally-curated classification already on the wire. HAM tags
# primary_instruments (the founding item carried EQ:US:SPY); DJN tags Dow Jones
# topic codes. Either is worth more than any keyword list we can write.
MACRO_INSTRUMENTS = {
    'EQ:US:SPY', 'EQ:US:QQQ', 'EQ:US:IWM', 'EQ:US:DIA',
    'EQ:US:TLT', 'EQ:US:TBT', 'EQ:US:IEF', 'EQ:US:SHY', 'EQ:US:GLD',
    'EQ:US:UUP', 'EQ:US:TMF', 'EQ:US:TMV',
}
MACRO_TOPICS = {
    'tsy',   # Treasury securities
    'bon',   # bonds
    'irt',   # interest rates
    'mon',   # monetary policy
    'gvu',   # government / public finance
    'sdt',   # sovereign debt
    'fxtr',  # FX trading
}

# -- L7: CALENDAR PRIOR -------------------------------------------------------
# The quarterly refunding announcement is the 1st Wednesday of Feb/May/Aug/Nov
# at 08:30 ET. Financing estimates land the Monday before. Outside these
# windows the poller idles; inside them it runs hot and the score floor drops.
QRA_MONTHS = (2, 5, 8, 11)
HOT_WINDOWS_ET = [('08:25', '09:15'), ('10:55', '11:10'), ('14:55', '15:10')]
HOT_INTERVAL_S = 15.0
COLD_INTERVAL_S = 120.0

# -- L1: DEDUP ----------------------------------------------------------------
# FTI republished one headline SIX times on 08/19 with delivery lags from 11
# seconds to 7 hours; DJN emitted the same Market Talk three times inside the
# same second. Dedup on a normalised headline, not on the message id.
DEDUP_WINDOW_S = 3600.0
CONFIRM_WINDOW_S = 900.0      # L9: a 2nd independent source inside 15 minutes

# L8 -- STORY COOLDOWN. Dedup catches a repeated HEADLINE. It does not catch
# the twelve DIFFERENT headlines every outlet writes about one event: on 08/19
# the buyback story generated 23 distinct alerting headlines between 08:36 and
# 20:43, and 22 of them told us nothing the first one had not.
#
# Once a concept has alerted, further items on that same concept are demoted to
# CONFIRM for the cooldown -- UNLESS they carry a figure we have not seen. That
# exception is load-bearing: it is what preserved 08:38:40 "$2B per operation
# will be at least $4B", which arrived 2m22s after the first headline and was
# the number the trade actually sized on.
# SLIDING: it measures silence since the last mention, not time since the
# first alert. Swept against the capture -- 1800s -> 27 alerts, 3600s -> 22,
# 7200s -> 7. Seven is the whole two-day capture and every one is a distinct
# tradeable event, so 7200 is the default. Lower it if you would rather be
# told that a story you already know about is still developing.
STORY_COOLDOWN_S = 7200.0

# L10 -- how long a story stays OPEN for same-source continuations to attach.
# Tighter than the cooldown: a figure arriving from the same desk 2 minutes
# later is a continuation, one arriving 25 minutes later is a new thought.
CONTINUATION_WINDOW_S = 600.0

# One EVENT, not one word. Every debt-supply term collapses to a single story
# family, so "liquidity support" at 08:36, "long-end" at 08:52 and "buyback" at
# 09:21 are recognised as the same story rather than three of them.
STORY_FAMILY = {
    'liquidity support': 'debt_supply', 'buyback': 'debt_supply',
    'buy-back': 'debt_supply', 'repurchase operation': 'debt_supply',
    'long-end': 'debt_supply', 'longer-dated': 'debt_supply',
    'nominal coupon': 'debt_supply', 'auction size': 'debt_supply',
    'auction sizes': 'debt_supply', 'coupon issuance': 'debt_supply',
    'quarterly refunding': 'debt_supply', 'refunding': 'debt_supply',
    'bill supply': 'debt_supply', 'issuance guidance': 'debt_supply',
    'marketable borrowing': 'debt_supply', 'financing estimates': 'debt_supply',
    'debt management': 'debt_supply', 'qra': 'debt_supply',
    'debt limit': 'debt_limit', 'extraordinary measures': 'debt_limit',
    'cash balance': 'tga_level', 'tga': 'tga_level',
    'tariff': 'trade', 'currency manipulat': 'fx_policy',
    'exchange rate report': 'fx_policy', 'fx report': 'fx_policy',
    'sanction': 'sanctions',
}

# -- SCORING ------------------------------------------------------------------
# An item must clear ALERT_FLOOR to raise a popup. Inside a hot window the
# floor drops by HOT_FLOOR_RELIEF -- the same asymmetry the earnings model uses
# around a scheduled print.
ALERT_FLOOR = 6.0
HOT_FLOOR_RELIEF = 2.0

# -- treasury.gov POLLER ------------------------------------------------------
# MEASURED, not assumed. Every home.treasury.gov URL costs 8-10s TTFB behind
# Akamai -- index, leaf, warm or cold -- and the edge IGNORES If-None-Match
# (a conditional GET returns 200, not 304). A 404 costs 38 SECONDS.
#
#   Server-Timing: cdn-cache; desc=REVALIDATE, edge; dur=9021, origin; dur=4
#
# The origin answers in 4 milliseconds. The 9 seconds is entirely Akamai.
# THIS IS WHY THERE IS NO 1-SECOND POLL. At 1 Hz you would have ten identical
# requests in flight at all times, every one returning the same edge-stale
# HTML, and you would be rate-limited inside a minute for it. The wire beat
# this page by design, not by luck.
PRESS_INDEX = 'https://home.treasury.gov/news/press-releases'
LEAF_FMT = 'https://home.treasury.gov/news/press-releases/%s'
HTTP_TIMEOUT_S = 30.0
USER_AGENT = 'shelnewsapi-treasury-monitor/0.1 (+kmusser@trlm.com)'
POLL_JITTER_S = 0.35

STATE_DIR = os.environ.get(
    'TREASURY_STATE_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state'))
LEDGER_PATH = os.path.join(STATE_DIR, 'ledger.json')
SEEN_PATH = os.path.join(STATE_DIR, 'seen.json')
