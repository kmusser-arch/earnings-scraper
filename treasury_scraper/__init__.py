"""Treasury / macro headline scraper.

Sibling to earnings_scraper. Same doctrine: everything configurable is read
once at startup, the hot path (a headline arriving) allocates almost nothing.

Founding case -- 2026-08-19, the long-end buyback expansion:

    08:36:18 ET  HAM   "$SPY U.S. Treasury increasing size of liquidity
                        support buyback operations for longer-dated nominal
                        coupon securities"                <- FIRST PRINT
    08:37:11 ET  HAM   "(more) ... Change is effective September 9."
    08:38:40 ET  HAM   "... $2B per operation will be at least $4B"
    08:44:10 ET  HAM   $TLT $TBT bond prices rising       <- tape moves, +8 min
    08:48:18 ET  SIN   "U.S. Treasury doubles buyback operation size"
    08:52:27 ET  FLY   "increased sizes of nominal long-end purchases"
    09:08:18 ET  WSJ   "Bond Yields Drop After Treasury ..."   <- +32 MINUTES

Every one of those timestamps came out of news.log, which was sitting in this
repo the whole time. The trade was not missed for lack of a scraper. It was
missed for lack of a FILTER -- 37,760 messages went past that day and the
three that mattered were inside the 5.8% of volume nobody was reading.
"""

__version__ = '0.1.0'
