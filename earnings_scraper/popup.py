"""The report-card pop-up.

★ This module does NOT format the scorecard. It displays, verbatim, whatever
`render_scorecard.render()` returns, in a monospace widget so the locked column
alignment survives. Every section this file used to build by hand -- hero table,
the four categories, the KPI grid, the gate block -- was a parallel formatter of
exactly that text, and two formatters drift.

Below the rendered block it appends the scraper-only diagnostics render() has no
field for (HARD 10, precedence detail, flag counts). Those are additive, never a
restatement, so the rendered region stays comparable to the chat path.

THREADING
=========
Tk is not thread-safe and must own the thread it was created on. The SDK invokes
the subscription callback on its own reader thread, so the callback never touches
a widget -- cards cross threads through a queue the main thread polls.
"""

import queue
import tkinter as tk
from tkinter import font as tkfont

BG = '#12151a'
BG_PANEL = '#1a1f27'
FG = '#e6edf3'
FG_DIM = '#8b949e'
GREEN = '#3fb950'
YELLOW = '#d29922'
RED = '#f85149'
BLUE = '#58a6ff'
ORANGE = '#db6d28'
PURPLE = '#bc8cff'

BAND_COLORS = {
    'DECISIVE_BULLISH': GREEN,
    'DECISIVE_BEARISH': RED,
    'STAY_FOR_CALL': YELLOW,
}

# Line-level colouring, by leading marker only. Deliberately shallow -- the
# renderer owns the content; this owns nothing but the paint.
_LINE_TAGS = (
    ('⛔', 'bad'), ('🔴', 'bad'), ('PROBLEM', 'bad'), ('HARD 10', 'bad'),
    ('⚠', 'warn'), ('⚡', 'warn'), ('🟡', 'warn'),
    ('★', 'note'), ('🟢', 'good'),
    ('NOT GRADED', 'dim'), ('caveat', 'dim'),
)


class CardPopup:
    def __init__(self, on_quit=None):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title('Earnings Scraper')
        self.queue = queue.Queue()
        self.on_quit = on_quit
        self._windows = []
        self._offset = 0

        self.mono = tkfont.Font(family='Consolas', size=10)
        self.mono_b = tkfont.Font(family='Consolas', size=10, weight='bold')
        self.h1 = tkfont.Font(family='Segoe UI', size=15, weight='bold')
        self.h2 = tkfont.Font(family='Segoe UI', size=10, weight='bold')
        self.body = tkfont.Font(family='Segoe UI', size=9)

    # --- thread-safe entry point ---------------------------------------------

    def submit(self, card):
        self.queue.put(card)

    def pump(self, interval_ms=15):
        try:
            while True:
                card = self.queue.get_nowait()
                try:
                    self.show(card)
                except Exception as exc:
                    print('[popup] render failed: %r' % exc)
        except queue.Empty:
            pass
        self.root.after(interval_ms, self.pump, interval_ms)

    def run(self, prewarm=True):
        if prewarm:
            self.prewarm()
        self.pump()
        self.root.mainloop()

    def prewarm(self):
        """Pay Tk's one-time costs offscreen.

        Measured 294 ms first render vs ~88 ms steady state, almost all of it
        Windows FONT FALLBACK on glyphs absent from Consolas. The rendered
        scorecard is full of them -- ★ 🟢 🟡 🔴 ⚠ ⚡ ⛔ ⟨⟩ — so the dummy text
        must contain them or it warms nothing that matters.
        """
        glyphs = ('★★★ 🟢🟡🔴 ⚠ ⚡ ⛔ ⟨DEFERRED — needs the call⟩ · → – — '
                  '\U0001f7e0\U0001f7e1')
        body = '\n'.join([glyphs] + [
            '   %-40s %10s %10s %12s  %s'
            % ('warmup metric %d ★★ with a long label' % i, '81.50', '84.00',
               '8.965 ($B)', '🟡 ⚠unverified') for i in range(10)] + [glyphs])
        try:
            self.show(dict(ticker='WARM', quarter='Q0', rendered=body,
                           diagnostics=[glyphs, 'HARD 10 — warm', '⚠ warm'],
                           wire='WARM', receivedAt='00:00:00', latencyMs=0.0,
                           gate=dict(band='STAY_FOR_CALL',
                                     overallBracket=[-0.4, 0.4])))
            win = self._windows.pop()
            win.geometry('+%d+%d' % (-4000, -4000))
            self.root.update()
            win.destroy()
            self.root.update()
            self._offset = 0
        except Exception as exc:
            print('[popup] prewarm skipped: %r' % exc)

    # --- rendering ------------------------------------------------------------

    def show(self, card):
        win = tk.Toplevel(self.root)
        self._windows.append(win)
        win.title('%s  %s' % (card.get('ticker', '?'), card.get('quarter') or ''))
        win.configure(bg=BG)

        self._offset = (self._offset + 26) % 160
        win.geometry('+%d+%d' % (120 + self._offset, 50 + self._offset))
        win.attributes('-topmost', True)
        win.lift()
        win.focus_force()
        win.bind('<Escape>', lambda e: win.destroy())
        try:
            win.bell()
        except tk.TclError:
            pass

        self._header(win, card)
        if card.get('error'):
            self._no_card(win, card)
        else:
            self._rendered(win, card)
        self._footer(win, card)

    def _header(self, parent, card):
        bar = tk.Frame(parent, bg=BG_PANEL)
        bar.pack(fill='x')
        left = tk.Frame(bar, bg=BG_PANEL)
        left.pack(side='left', padx=12, pady=8)
        tk.Label(left, text='%s  %s' % (card.get('ticker', '?'),
                                        card.get('quarter') or ''),
                 font=self.h1, bg=BG_PANEL, fg=FG, anchor='w').pack(anchor='w')
        sub = ' · '.join(x for x in (card.get('company'), card.get('sector'),
                                     card.get('wire')) if x)
        tk.Label(left, text=sub or '-', font=self.body, bg=BG_PANEL, fg=FG_DIM,
                 anchor='w').pack(anchor='w')

        g = card.get('gate') or {}
        band = g.get('band')
        if band:
            right = tk.Frame(bar, bg=BG_PANEL)
            right.pack(side='right', padx=14, pady=8)
            tk.Label(right, text=band, font=self.h2, bg=BG_PANEL,
                     fg=BAND_COLORS.get(band, FG)).pack()
            if g.get('overallBracket'):
                lo, hi = g['overallBracket']
                tk.Label(right, text='overall ∈ [%+.2f, %+.2f]' % (lo, hi),
                         font=self.body, bg=BG_PANEL, fg=FG_DIM).pack()

    def _rendered(self, parent, card):
        """The renderer's output, verbatim, plus additive diagnostics."""
        text = card.get('rendered')
        if not text:
            text = ('⛔ RENDERER UNAVAILABLE: %s\n\n'
                    'No local formatting is attempted — a parallel formatter '
                    'would drift from the chat path.'
                    % (card.get('renderError') or 'unknown'))

        diag = card.get('diagnostics') or []
        if diag:
            rule = '─' * 78
            text = '%s\n\n%s\nSCRAPER DIAGNOSTICS — not part of the locked ' \
                   'format\n%s\n%s' % (text, rule, rule, '\n'.join(diag))

        lines = text.split('\n')
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill='both', expand=True)
        widget = tk.Text(wrap, bg=BG, fg=FG, font=self.mono, wrap='none',
                         borderwidth=0, highlightthickness=0, padx=12, pady=10,
                         width=min(114, max(len(l) for l in lines) + 2),
                         height=min(46, len(lines) + 1))
        vbar = tk.Scrollbar(wrap, orient='vertical', command=widget.yview)
        hbar = tk.Scrollbar(wrap, orient='horizontal', command=widget.xview)
        widget.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        vbar.pack(side='right', fill='y')
        hbar.pack(side='bottom', fill='x')
        widget.pack(side='left', fill='both', expand=True)

        widget.tag_configure('good', foreground=GREEN)
        widget.tag_configure('warn', foreground=YELLOW)
        widget.tag_configure('bad', foreground=RED)
        widget.tag_configure('note', foreground=PURPLE)
        widget.tag_configure('dim', foreground=FG_DIM)
        widget.tag_configure('head', foreground=BLUE, font=self.mono_b)

        for i, line in enumerate(lines, start=1):
            widget.insert('end', line + '\n')
            tag = None
            stripped = line.strip()
            if stripped and not line.startswith(' ') and (
                    stripped.endswith('SCORECARD')
                    or stripped[:1].isdigit()
                    or stripped.startswith(('HERO KPIs', 'Overall Score',
                                            'SCRAPER DIAGNOSTICS'))):
                tag = 'head'
            else:
                for marker, t in _LINE_TAGS:
                    if marker in line:
                        tag = t
                        break
            if tag:
                widget.tag_add(tag, '%d.0' % i, '%d.end' % i)
        widget.configure(state='disabled')

    def _no_card(self, parent, card):
        """NO_CARD / NO_PROFILE. render() cannot help -- there is no record."""
        panel = tk.Frame(parent, bg=BG)
        panel.pack(fill='both', expand=True, padx=12, pady=10)
        tk.Label(panel, text='%s — %s' % (card.get('ticker'), card['error']),
                 font=self.h1, bg=BG, fg=RED, anchor='w').pack(fill='x')
        tk.Label(panel, text=card.get('message') or '', font=self.h2, bg=BG,
                 fg=ORANGE, anchor='w', wraplength=820,
                 justify='left').pack(fill='x', pady=(2, 6))
        tk.Label(panel, text='Numbers extracted and displayed. NOTHING GRADED '
                             '— a confidently wrong grade propagates into '
                             'beatMagnitude and branchAccuracyLog.',
                 font=self.body, bg=BG, fg=FG_DIM, anchor='w', wraplength=820,
                 justify='left').pack(fill='x')
        raw = card.get('rawFigures') or {}
        if raw:
            box = tk.Frame(panel, bg=BG_PANEL)
            box.pack(fill='x', pady=(8, 0))
            for k, v in raw.items():
                tk.Label(box, text='  %-26s %s' % (k, v), font=self.mono,
                         bg=BG_PANEL, fg=FG, anchor='w').pack(fill='x')
        if card.get('headline'):
            tk.Label(panel, text=card['headline'], font=self.body, bg=BG,
                     fg=FG_DIM, anchor='w', wraplength=820,
                     justify='left').pack(fill='x', pady=(8, 0))

    def _footer(self, parent, card):
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill='x', padx=12, pady=8)
        bits = [card.get('wire') or '']
        if card.get('latencyMs') is not None:
            bits.append('detect→card %.1f ms' % card['latencyMs'])
        if card.get('receivedAt'):
            bits.append(card['receivedAt'])
        if card.get('recordId'):
            bits.append(card['recordId'])
        tk.Label(bar, text='  |  '.join(b for b in bits if b), font=self.mono,
                 bg=BG, fg=FG_DIM, anchor='w').pack(side='left')
        tk.Button(bar, text='Close  (Esc)', command=parent.destroy, bg=BG_PANEL,
                  fg=FG, font=self.body, relief='flat', padx=12,
                  pady=3).pack(side='right')
