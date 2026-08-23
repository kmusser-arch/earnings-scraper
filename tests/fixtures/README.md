# Wire fixtures

Real messages captured from the SHEL News Gateway, extracted from
`news.log` (which is gitignored: it grows every run).

`wire_messages.jsonl` -- 317 messages, UTF-8, one JSON object per
line. `subscribed.json` -- the session handshake, listing the 39
entitled sources.

## Why real messages

Every harness bug in this project came from a SYNTHESISED message
asserting a shape the wire does not guarantee. The worst wrote
"$1923.686 billion" from a value stored in $M and made a correct
pipeline look broken for two rounds.

## Why the sample is stratified

The revision classes are rare -- 47 `update` and 217
`minor-update` out of 21,660 news_items -- so a first-N sample
would contain none of them. All 47 `update` messages are kept.

## Two traps these fixtures encode

1. `news.log` is **UTF-16LE**. Reading it as UTF-8 or cp1252
   yields zero parseable messages and looks like an empty log.
   The fixture is UTF-8 so it cannot repeat that.
2. Headlines mode carries **no body**: `body`, `text`, `story`,
   `url` and `link` are populated 0 times across all 21660 captured
   news_items. There is also no fetch-by-id API on the client, so
   `mode='full'` is the only way to get a release body.

## Composition

```
total                    317
update                   47
minor_update             60
first_with_instruments   120
first_without            60
edgar                    20
court                    10
```
