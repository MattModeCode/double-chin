"""The fixed scripts a sweep synthesizes.

Two of them, and they are deliberately plain prose: no `[pause:N]`, no
`*emphasis*`. Emphasis markup raises exaggeration and lowers cfg_weight for
the spanned chunk (see `engine.synthesize`), and those adjustments clamp at
the knob's range — so a marked-up script would distort exactly the candidates
sitting near the ends of the grid. Delivery marks layer on top of whatever
profile wins; they are not part of what is being measured.

Both are kept to a single chunk (under `chunk.DEFAULT_MAX_CHARS`, about ten
seconds of audio). Length is pure cost here: every candidate is synthesized
several times over, and a longer passage buys no extra signal for metrics
that compare sets of clips.

`TUNING` drives the search. `HOLDOUT` is never searched on — it is only used
to re-score the winner, which is what catches a profile that has quietly
overfit to one passage.
"""

from __future__ import annotations

TUNING = (
    "I keep a running list of things I meant to fix, and it gets longer every "
    "week. Most of them are small. The rest I have been putting off since March."
)

HOLDOUT = (
    "The part nobody tells you about building your own tools is how much of it "
    "is deciding what to leave out. I spent an afternoon on one, then deleted it."
)

TUNING_SCRIPTS = {"tuning": TUNING, "holdout": HOLDOUT}
