"""Runtime access to the model: library, profiles, calibration.

The scraper never parses markdown. All three runtime inputs are JSON.

THE CARD IS THE CONFIG FILE
===========================
There is no separate config. Each morning a record is written into
`earnings-library.json` with `status: "PRE-EARNINGS"` carrying the consensus,
the bogeys, the keyKPI list in its load-bearing order, the positioning axis and
a scenario ladder. The scraper is strictly DOWNSTREAM of that build and cannot
score a name with no card.
"""

import json
import os
import re

from . import config


def _canonical(pre_rows):
    """Fill name/consensus from the renderer's alias functions. Copies only."""
    from . import scorecard
    return scorecard.canonicalise_kpis(pre_rows)


class NoCard(Exception):
    """No PRE-EARNINGS card for this ticker today."""


class NoProfile(Exception):
    """No hero-KPI profile for this ticker."""


def _load(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


class Model:
    """Loaded once at startup; held in memory for the trading day."""

    def __init__(self, library_path=None, profiles_path=None,
                 calibration_path=None):

        # ★ Prove the encoding before reading anything. A mandatory gate in this
        # toolchain never ran for months because a bare open() could not decode
        # this file; the diagnostic travels on the model so a card can carry it.
        self.encodingNotes = config.preflight()
        self.library_path = library_path or config.LIBRARY_PATH
        self.profiles_path = profiles_path or config.PROFILES_PATH
        self.calibration_path = calibration_path or config.CALIBRATION_PATH

        self.library = _load(self.library_path)
        self.profiles = (_load(self.profiles_path) or {}).get('profiles', {})
        self.calibration = _load(self.calibration_path)

        # `abandonedRecords[]` holds pre-earnings cards that were built and
        # never scored. They must NOT be indexed and must NOT be counted in
        # records[].
        self.records = self.library.get('records') or []
        self.abandoned = self.library.get('abandonedRecords') or []

        # Frameworks are read from the library at runtime and never duplicated
        # into code, so a framework revision propagates without a code change.
        self.frameworks = {k: self.library.get(k) for k in (
            'positioningFramework', 'scenarioLadderFramework',
            'beatMagnitudePatterns', 'overnightHoldFramework',
            'regimeFramework', 'branchAccuracyLog', 'currentRegime',
            'prOnlyGateFramework', 'forwardCommitmentSchema',
            'forwardCommitmentFindings', 'fyInlineIsBearish',
            'schemaNotes') if self.library.get(k) is not None}

        self.weights = self.calibration.get('weights') or config.WEIGHTS
        self.cq_bands = self.calibration.get('currentQuarterBands') or []
        self.offsetting_flags = self.calibration.get('offsettingFlags') or []

    # --- counts, for the startup report ---------------------------------------

    def counts(self):
        import collections
        units = collections.Counter(
            (r.get('preEarnings') or {}).get('revUnit') for r in self.records)
        legacy = self._legacy_ids()
        return dict(
            records=len(self.records),
            abandoned=len(self.abandoned),
            profiles=len(self.profiles),
            revUnitNull=units.get(None, 0),
            revUnitB=units.get('$B', 0),
            revUnitM=units.get('$M', 0),
            pinningSet=len([r for r in self.reported_records()
                            if r['id'] not in legacy]),
            pendingCards=len(self.records) - len(self.reported_records()),
            calibrationRecordsUsed=self.calibration.get('recordsUsed'),
            libraryVersion=self.library.get('version'),
            libraryLastUpdated=self.library.get('lastUpdated'),
        )

    def _legacy_ids(self):
        """Resolve `legacyNonHalfStepRecords` ("MDB +1.4") to record ids.

        ★ MATCHED BY TICKER, SCOPED TO REPORTED RECORDS. Keying on the score
        as well would be precise, but every score in the list is STALE -- "MDB
        +1.4" against a record scoring 1.6, "AVGO +1.4" against 0.53 -- so
        score-matching finds nothing and silently empties the exclusion set.

        ⚠ CONSEQUENCE, and it is a real trap: while those figures disagree with
        the records the exclusion stays ticker-wide, so a SECOND reported
        quarter for any of these seven tickers will drop out of the pinning set
        without a word. Fixing that means correcting the scores in
        calibration.json, which is a data decision.
        """
        out = set()
        for entry in self.calibration.get('legacyNonHalfStepRecords') or []:
            ticker = str(entry).split()[0].upper()
            for rec in self.reported_records():
                if (rec.get('ticker') or '').upper() == ticker:
                    out.add(rec['id'])
        return out

    def reported_records(self):
        """Records with an outcome. A PRE-EARNINGS card pins nothing.

        ★ The half-step pinning set is drawn from prints that HAPPENED. A card
        built this morning for tonight's print has no actuals and no scores, so
        counting it broke the one invariant that must hold -- and the warning
        told the operator to regenerate calibration.json, which would have
        rewritten the 69 records that pin the model.
        """
        return [r for r in self.records
                if str(r.get('status') or '').upper() != 'PRE-EARNINGS']

    def check_invariant(self):
        """calibration.recordsUsed must equal the half-step pinning-set size.

        Counts move; the doc is not authoritative. This is the ONE invariant
        that must hold -- if it diverges, regenerate the calibration rather
        than adjusting tests.
        """
        c = self.counts()
        ok = c['pinningSet'] == c['calibrationRecordsUsed']
        return ok, ('pinning set %s vs calibration.recordsUsed %s'
                    % (c['pinningSet'], c['calibrationRecordsUsed']))

    def pinning_records(self):
        legacy = self._legacy_ids()
        return [r for r in self.reported_records()
                if r['id'] not in legacy]

    # --- the index ------------------------------------------------------------

    def index_for(self, today):
        """{TICKER: record} for cards reporting `today` and not yet scored.

        Case-insensitive on status: a lowercase 'pre-earnings' once made the
        dashboard's `isPre` false, and because `null >= 0` is true in
        JavaScript the header called .toFixed() on null and three cards became
        un-openable.
        """
        idx = {}
        for rec in self.records:
            if str(rec.get('status', '')).upper() != 'PRE-EARNINGS':
                continue
            if rec.get('reportDate') != today:
                continue
            idx[(rec.get('ticker') or '').upper()] = rec
        return idx

    def record_by_id(self, record_id):
        for rec in self.records:
            if rec.get('id') == record_id:
                return rec
        return None

    def latest_record(self, ticker):
        """Newest record for a ticker, REGARDLESS of status.

        For selftest and regression pinning only -- never for live grading,
        which must go through index_for(today).
        """
        matches = [r for r in self.records
                   if (r.get('ticker') or '').upper() == ticker.upper()]
        matches.sort(key=lambda r: (r.get('reportDate') or '',
                                    r.get('updatedAt') or ''), reverse=True)
        return matches[0] if matches else None

    # --- hero KPI selection ---------------------------------------------------

    def hero_for(self, ticker, applies_to='currentQuarter'):
        """The priority-1 hero KPI for a category.

        Raises NoProfile when the ticker has no profile. Refusing is correct:
        revenue-based grading provably cannot reproduce the accepted grades, so
        a revenue fallback produces a CONFIDENTLY WRONG score, which is worse
        than a blank because it propagates into beatMagnitude and
        branchAccuracyLog.
        """
        prof = self.profiles.get(ticker.upper())
        if prof is None:
            raise NoProfile('%s: no hero-KPI profile' % ticker)
        heroes = [h for h in (prof.get('heroKPIs') or [])
                  if h.get('priority') == 1
                  and h.get('appliesTo') == applies_to]
        return heroes, prof

    def prepare(self, ticker, today, allow_any_status=False):
        """Resolve everything the scorer needs, or raise.

        `allow_any_status` is for selftest only, and resolves the NEWEST record
        for the ticker. Regression pinning must use prepare_from_record instead
        -- several tickers have more than one record (TSLA has Q1 and Q2), and
        "latest by ticker" silently grades the wrong quarter.
        """
        ticker = ticker.upper()
        if allow_any_status:
            rec = self.latest_record(ticker)
        else:
            rec = self.index_for(today).get(ticker)
        if rec is None:
            raise NoCard('%s: no pre-earnings card' % ticker)
        return self.prepare_from_record(rec)

    def prepare_from_record(self, rec):
        # ★ A record the library declares unscoreable is refused HERE, with its
        # own stated reason, rather than failing later on a missing key.
        ex = (rec or {}).get('preEarningsAbsent')
        if ex:
            raise NoCard(
                '%s: %s' % (rec.get('id'),
                            ex.get('consequence') or ex.get('reason')
                            or 'preEarningsAbsent'))
        
        """Resolve a specific record. Exact, no ticker-level ambiguity."""
        ticker = (rec.get('ticker') or '').upper()
        heroes, prof = self.hero_for(ticker, 'currentQuarter')
        pe = rec.get('preEarnings') or {}
        pa = rec.get('positioningAxis') or {}

        # score10 vs score10Estimate are DIFFERENT KEYS. Read score10 first,
        # fall back to the estimate, and surface confidence so a 1/6 estimate
        # never displays as though it were 6/6.
        score10 = pa.get('score10')
        score10_is_estimate = False
        if score10 is None:
            score10 = pa.get('score10Estimate')
            score10_is_estimate = score10 is not None

        return dict(
            ticker=ticker,
            recordId=rec.get('id'),
            # THE DERIVED PERIOD TRAVELS WITH THE ENTRY. `quarter` spells
            # itself fifteen ways and `year` three; re-parsing them at the
            # point of use is what made one field mean three things.
            fiscalQuarter=rec.get('fiscalQuarter'),
            fiscalYear=rec.get('fiscalYear'),
            company=rec.get('company') or '',
            sector=rec.get('sector') or '',
            quarter=rec.get('quarter') or '',
            year=rec.get('year') or '',
            reportDate=rec.get('reportDate') or '',
            timing=rec.get('timing') or '',
            status=rec.get('status'),
            # expectations
            revConsensus=pe.get('revConsensus'),
            revBogey=pe.get('revBogey'),
            revUnit=pe.get('revUnit'),
            epsConsensus=pe.get('epsConsensus'),
            epsBogey=pe.get('epsBogey'),
            impliedMove=pe.get('impliedMove'),
            impliedMovePct=parse_implied_move(pe.get('impliedMove')),
            bogeyMethod=pe.get('bogeyMethod'),
            bogeyReliability=pe.get('bogeyReliability'),
            whatMattersMost=pe.get('whatMattersMost'),
            setup=pe.get('setup'),
            bullCase=pe.get('bullCase'),
            bearCase=pe.get('bearCase'),
            nextQGuideExpected=pe.get('nextQGuideExpected'),
            fyGuideExpected=pe.get('fyGuideExpected'),
            # Structured forward expectations. The schema varies by ticker and
            # q2Expectations is a bare STRING on some records, so callers must
            # isinstance-check before using them.
            fyExpectations=pe.get('fyExpectations'),
            q2Expectations=pe.get('q2Expectations'),
            # ORDER IS LOAD-BEARING
            # ★ Canonicalised on the way in: 31 library rows name the metric
            # 'metric' and the street 'cons'. Done here so no downstream reader
            # can miss it, using the renderer's own alias functions.
            keyKPIs=_canonical(pe.get('keyKPIs') or []),
            # profile
            heroes=heroes,
            heroName=heroes[0]['name'] if heroes else None,
            profile=prof,
            needsReview=bool(prof.get('needsReview')),
            allHeroes=prof.get('heroKPIs') or [],
            # positioning
            positioningAxis=pa,
            score10=score10,
            score10IsEstimate=score10_is_estimate,
            positioningConfidence=pa.get('confidence'),
            componentsScored=pa.get('componentsScored'),
            signModifier=pa.get('signModifier'),
            band=pa.get('band'),
            # context
            scenarioLadder=rec.get('scenarioLadder') or [],
            priorQuarter=rec.get('priorQuarter'),
            stockContext=rec.get('stockContext'),
            marketRegime=rec.get('marketRegime'),
            # The tail separator. Present on only 12 of 76 records, so every
            # consumer must gate on presence.
            forwardCommitment=rec.get('forwardCommitment'),
            # ⚡ The asymmetric event flag. render() puts this at the very TOP
            # of the card when it fires, so it MUST be carried forward from the
            # pre-earnings build. 22 of 76 records set it; 5 more carry the
            # weaker `asymmetricEventWatch`.
            #
            # Carried forward, NEVER detected from the release: firing it needs
            # the three B6 gates (MAGNITUDE, HORIZON, FORCEFUL) on a
            # vague-but-quantitative forward claim lacking a dollar anchor,
            # which is narrative judgment and sits in the do-not-automate list.
            asymmetricEventFlag=rec.get('asymmetricEventFlag'),
            asymmetricEventWatch=rec.get('asymmetricEventWatch'),
        )


_IMPLIED = re.compile(r'([\d.]+)\s*%')


def parse_implied_move(text):
    """Pull the leading percentage out of e.g. "±15.6% (~±$17)"."""
    if not text:
        return None
    m = _IMPLIED.search(str(text))
    return float(m.group(1)) if m else None
