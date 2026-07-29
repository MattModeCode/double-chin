#!/usr/bin/env python3
"""Generate a voice passport: a provenance card for an enrolled voice.

A voice passport states what a cloned voice was built from, how it is
verified, and what marks its outputs carry — the paperwork a cloned voice
should never travel without.

Usage:
    .venv/bin/python demo/make_voice_passport.py VOICE_NAME OUT.html \
        [--score 0.921] [--score-label "vs holdout, via Studio"]

Reads the voice's meta.json from DOUBLECHIN_HOME (default ~/.double-chin); pass a
measured similarity score to stamp it on the card.
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from double_chin.config import voices_dir

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>voice passport · {name}</title>
<style>
  body{{background:#0a0a0f;color:#e2e8f0;font-family:"JetBrains Mono","Menlo",monospace;
      font-size:14px;line-height:1.6;display:flex;justify-content:center;
      align-items:center;min-height:100vh;margin:0;padding:24px}}
  .card{{background:#0f0f14;border:1px solid rgba(226,232,240,.12);border-radius:8px;
       max-width:560px;width:100%;padding:36px 40px;
       box-shadow:0 4px 16px rgba(0,0,0,.5)}}
  .head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}}
  h1{{font-size:22px;font-weight:500;margin:0;letter-spacing:-.01em}}
  .eyebrow{{color:#94a3b8;font-size:11px;letter-spacing:.12em;text-transform:uppercase}}
  .mark{{width:34px;height:34px;border-radius:8px;background:#0f0e13;display:flex;
       align-items:flex-end;justify-content:center;gap:2.5px;padding:8px 0 7px}}
  .mark span{{width:3.5px;background:#e1e0e0;border-radius:2px;display:block}}
  .mark span:nth-child(1),.mark span:nth-child(5){{height:32%}}
  .mark span:nth-child(2),.mark span:nth-child(4){{height:62%}}
  .mark span:nth-child(3){{height:100%}}
  dl{{display:grid;grid-template-columns:auto 1fr;gap:8px 20px;margin:26px 0}}
  dt{{color:#94a3b8;font-size:12px}}
  dd{{margin:0;font-size:13px}}
  .score{{color:#22c55e}}
  .foot{{border-top:1px solid rgba(226,232,240,.08);padding-top:16px;color:#475569;
       font-size:11.5px}}
  .foot p{{margin:0 0 8px}}
</style></head><body>
<div class="card">
  <div class="head">
    <div><div class="eyebrow">voice passport</div><h1>{name}</h1></div>
    <div class="mark" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span></div>
  </div>
  <dl>
    <dt>enrolled</dt><dd>{created}</dd>
    <dt>reference</dt><dd>{duration:.1f} s · mono · {sample_rate} Hz · peak-normalized</dd>
    <dt>built from</dt><dd>{source_count} recording{plural}</dd>
    <dt>holdout</dt><dd>{holdout}</dd>
    <dt>verification</dt><dd>{verification}</dd>
    <dt>engine</dt><dd>Chatterbox TTS 0.5B (MIT) · zero-shot conditioning, never trained on this voice</dd>
    <dt>watermark</dt><dd>Resemble Perth on every output — provenance signal, not a control</dd>
    <dt>storage</dt><dd>this machine only: DOUBLECHIN_HOME/voices/{name}/</dd>
  </dl>
  <div class="foot">
    <p>Deleting the voice folder revokes this voice entirely; no model weights remember it.</p>
    <p>Clone only a voice you have the right to clone. Issued {issued} by Double Chin.</p>
  </div>
</div>
</body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("out", type=Path)
    parser.add_argument("--score", type=float, default=None)
    parser.add_argument("--score-label", default="vs holdout")
    args = parser.parse_args()

    meta_path = voices_dir() / args.name / "meta.json"
    meta = json.loads(meta_path.read_text())

    has_holdout = (voices_dir() / args.name / "holdout.wav").is_file()
    holdout = (
        "reserved — outputs are scored against audio the model never conditions on"
        if has_holdout
        else "none — outputs are scored against the reference itself"
    )
    if args.score is not None:
        verification = (
            f'<span class="score">{args.score:.3f}</span> cosine similarity '
            f"({html.escape(args.score_label)}, resemblyzer GE2E; "
            f"match ≥ 0.75, wrong-speaker floor ≈ 0.7)"
        )
    else:
        verification = "not yet measured — run a generation with verify"

    source_count = len(meta["source_files"])
    args.out.write_text(
        PAGE.format(
            name=html.escape(meta["name"]),
            created=meta["created"][:10],
            duration=meta["duration_seconds"],
            sample_rate=meta["sample_rate"],
            source_count=source_count,
            plural="s" if source_count != 1 else "",
            holdout=holdout,
            verification=verification,
            issued=datetime.now(timezone.utc).date().isoformat(),
        )
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
