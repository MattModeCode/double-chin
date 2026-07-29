#!/usr/bin/env python3
"""Build a Double Chin speech-style profile from one or more reference recordings.

Transcribes the given audio with word-level timestamps (mlx-whisper), then
derives the statistics `double-chin-perform` needs to rewrite a plain script into
a performance script: filler-word rate, pause-tier durations, clause length,
speaking rate, and recommended delivery knobs (exaggeration / cfg /
temperature).

Run with the skill's own venv, not the system interpreter:
    .claude/skills/double-chin-perform/.venv/bin/python scripts/profile_audio.py \
        "~/Downloads/New Recording 63.m4a"

Writes profile.json (machine-readable) and profile.md (human-readable) under
$DOUBLECHIN_HOME/style/ (default ~/.double-chin/style/).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import mlx_whisper
except ImportError:
    print(
        "mlx-whisper is not installed in this interpreter.\n"
        "Run this script with the skill's bundled venv:\n"
        "  .claude/skills/double-chin-perform/.venv/bin/python "
        "scripts/profile_audio.py <audio...>\n"
        "(or install it yourself: python3 -m pip install mlx-whisper)",
        file=sys.stderr,
    )
    raise SystemExit(1)

WHISPER_MODEL = "mlx-community/whisper-small.en-mlx"

# Fillers/discourse markers to track, longest phrases first so multi-word
# markers are not shadowed by single-word ones during counting.
_FILLERS = [
    "you know", "i mean", "kind of", "sort of",
    "um", "uh", "umm", "uhh", "like", "so", "right",
    "actually", "basically", "literally", "honestly", "well",
]


@dataclass
class Word:
    text: str
    start: float
    end: float
    segment_final: bool


@dataclass
class Profile:
    sources: list[str]
    built_at: str
    duration_seconds: float
    word_count: int
    words_per_minute: float
    clause_words: dict[str, float]
    fillers_per_100w: dict[str, float]
    pause_tiers_seconds: dict[str, float]
    elongation_candidates: list[dict] = field(default_factory=list)
    recommended_knobs: dict[str, float] = field(default_factory=dict)
    transcript: str = ""

    def to_json(self) -> dict:
        return {
            "sources": self.sources,
            "built_at": self.built_at,
            "duration_seconds": round(self.duration_seconds, 2),
            "word_count": self.word_count,
            "words_per_minute": round(self.words_per_minute, 1),
            "clause_words": {k: round(v, 2) for k, v in self.clause_words.items()},
            "fillers_per_100w": {k: round(v, 2) for k, v in self.fillers_per_100w.items() if v > 0},
            "pause_tiers_seconds": {k: round(v, 3) for k, v in self.pause_tiers_seconds.items()},
            "elongation_candidates": self.elongation_candidates,
            "recommended_knobs": self.recommended_knobs,
            "transcript": self.transcript,
        }


def transcribe(audio_path: Path) -> dict:
    return mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=WHISPER_MODEL,
        word_timestamps=True,
        verbose=False,
    )


def _flatten_words(result: dict) -> list[Word]:
    words: list[Word] = []
    for segment in result["segments"]:
        seg_words = segment.get("words", [])
        for i, w in enumerate(seg_words):
            text = w["word"].strip()
            if not text:
                continue
            segment_final = i == len(seg_words) - 1
            words.append(Word(text=text, start=float(w["start"]), end=float(w["end"]), segment_final=segment_final))
    return words


def _inter_word_gaps(words: list[Word]) -> list[float]:
    """Return every positive inter-word gap in seconds, across the whole
    sequence. (We deliberately don't split these by whether the preceding
    word was a detected sentence end: whisper often folds trailing silence
    into a segment-final word's own end timestamp, which starves that
    bucket and makes tiers come out non-monotonic. Pooling all gaps and
    taking quantiles is more robust to that artifact.)"""
    gaps = []
    for prev, nxt in zip(words, words[1:]):
        gap = nxt.start - prev.end
        if gap > 0:
            gaps.append(gap)
    return gaps


def _pause_tiers(gaps: list[float]) -> dict[str, float]:
    """Derive four escalating pause tiers from the speaker's own gap
    distribution via quantiles, so ordering is guaranteed regardless of how
    the speaker actually distributes pauses (some speakers pause more
    within a clause than at a sentence end)."""
    defaults = {"micro": 0.15, "short": 0.35, "sentence": 0.5, "beat": 0.85}
    if not gaps:
        return defaults

    def pct(data: list[float], p: float) -> float:
        data = sorted(data)
        idx = min(len(data) - 1, int(len(data) * p))
        return data[idx]

    micro = pct(gaps, 0.25)
    short = max(pct(gaps, 0.50), micro + 0.05)
    sentence = max(pct(gaps, 0.75), short + 0.05)
    beat = max(pct(gaps, 0.92), sentence + 0.1)
    return {"micro": micro, "short": short, "sentence": sentence, "beat": beat}


def _filler_rates(text: str, word_count: int) -> dict[str, float]:
    lowered = f" {text.lower()} "
    rates: dict[str, float] = {}
    for phrase in _FILLERS:
        pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
        count = len(re.findall(pattern, lowered))
        rates[phrase] = (count / word_count * 100) if word_count else 0.0
    return rates


def _clause_lengths(result: dict) -> dict[str, float]:
    lengths = [len(seg["text"].split()) for seg in result["segments"] if seg["text"].strip()]
    if not lengths:
        return {"mean": 0.0, "sd": 0.0}
    mean = statistics.fmean(lengths)
    sd = statistics.pstdev(lengths) if len(lengths) > 1 else 0.0
    return {"mean": mean, "sd": sd}


def _elongation_candidates(words: list[Word], limit: int = 8) -> list[dict]:
    """Flag words the speaker held noticeably longer than their length predicts.

    A crude per-character duration ratio; outliers are words worth writing
    with stretched letters (e.g. "so" -> "sooo") to cue the TTS reader.

    Segment-final words are excluded: whisper routinely folds trailing
    silence (a breath, a thinking pause) into the last word's end
    timestamp, which would otherwise masquerade as elongation on short
    function words ("or", "in", "to") rather than real vocal stretching.
    Short words are excluded too — a duration artifact on a 2-letter word
    swings its char-normalized ratio wildly even after that filter.
    """
    scored = []
    for w in words:
        if w.segment_final:
            continue
        clean = re.sub(r"[^a-zA-Z]", "", w.text)
        if len(clean) < 4:
            continue
        duration = w.end - w.start
        if duration <= 0:
            continue
        ratio = duration / len(clean)
        scored.append((ratio, clean, duration))
    if not scored:
        return []
    ratios = [r for r, _, _ in scored]
    baseline = statistics.median(ratios)
    threshold = baseline * 2.2
    outliers = sorted((s for s in scored if s[0] > threshold), key=lambda s: -s[0])
    seen: set[str] = set()
    result = []
    for ratio, word, duration in outliers:
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append({"word": word, "duration_seconds": round(duration, 2), "ratio_vs_baseline": round(ratio / baseline, 2)})
        if len(result) >= limit:
            break
    return result


def _recommended_knobs(wpm: float) -> dict[str, float]:
    """Seed delivery knobs from speaking rate; cfg/temperature favour fidelity
    over variety since the goal is matching one specific voice, not novelty."""
    if wpm >= 165:
        exaggeration = 0.65
    elif wpm <= 115:
        exaggeration = 0.35
    else:
        exaggeration = 0.5
    return {"exaggeration": exaggeration, "cfg": 0.65, "temperature": 0.7}


def build_profile(audio_paths: list[Path]) -> Profile:
    all_words: list[Word] = []
    all_text: list[str] = []
    all_segments: list[dict] = []
    total_duration = 0.0

    for path in audio_paths:
        result = transcribe(path)
        words = _flatten_words(result)
        all_words.extend(words)
        all_text.append(result["text"].strip())
        all_segments.extend(result["segments"])
        if words:
            total_duration += words[-1].end - words[0].start

    word_count = len(all_words)
    wpm = (word_count / total_duration * 60) if total_duration > 0 else 0.0
    gaps = _inter_word_gaps(all_words)
    transcript = " ".join(all_text)

    return Profile(
        sources=[p.name for p in audio_paths],
        built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        duration_seconds=total_duration,
        word_count=word_count,
        words_per_minute=wpm,
        clause_words=_clause_lengths({"segments": all_segments}),
        fillers_per_100w=_filler_rates(transcript, word_count),
        pause_tiers_seconds=_pause_tiers(gaps),
        elongation_candidates=_elongation_candidates(all_words),
        recommended_knobs=_recommended_knobs(wpm),
        transcript=transcript,
    )


def _double_chin_home() -> Path:
    """Reuse Double Chin's own home-dir convention (DOUBLECHIN_HOME env, else ~/.double-chin)
    so the style profile lives next to enrolled voices without duplicating
    that logic. Falls back to the same default if double_chin isn't importable."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))
        from double_chin.config import double_chin_home
        return double_chin_home()
    except ImportError:
        import os
        env_value = os.environ.get("DOUBLECHIN_HOME")
        return Path(env_value).expanduser() if env_value else Path.home() / ".double-chin"


def render_markdown(profile: Profile) -> str:
    lines = [
        "# Double Chin speech-style profile",
        "",
        f"Built {profile.built_at} from: {', '.join(profile.sources)}",
        "",
        f"- Speaking rate: **{profile.words_per_minute:.0f} wpm** over {profile.duration_seconds:.0f}s ({profile.word_count} words)",
        f"- Clause length: **{profile.clause_words['mean']:.1f} words** (±{profile.clause_words['sd']:.1f})",
        "",
        "## Pause tiers (seconds)",
        "",
        "| Tier | Duration | Lever to use |",
        "|---|---|---|",
        f"| micro | {profile.pause_tiers_seconds['micro']:.2f}s | comma |",
        f"| short | {profile.pause_tiers_seconds['short']:.2f}s | em-dash / ellipsis |",
        f"| sentence | {profile.pause_tiers_seconds['sentence']:.2f}s | end sentence (+0.35s engine pause) |",
        f"| beat | {profile.pause_tiers_seconds['beat']:.2f}s | paragraph break (+0.7s engine pause) |",
        "",
        "## Fillers (per 100 words)",
        "",
    ]
    fillers = {k: v for k, v in profile.fillers_per_100w.items() if v > 0}
    if fillers:
        for phrase, rate in sorted(fillers.items(), key=lambda kv: -kv[1]):
            lines.append(f"- \"{phrase}\": {rate:.1f}")
    else:
        lines.append("- none detected above noise floor")
    lines += ["", "## Elongation candidates", ""]
    if profile.elongation_candidates:
        lines.append("Words held noticeably longer than their length predicts — candidates for stretched-letter spelling (e.g. \"so\" -> \"sooo\"):")
        lines.append("")
        for c in profile.elongation_candidates:
            lines.append(f"- \"{c['word']}\" — {c['duration_seconds']:.2f}s ({c['ratio_vs_baseline']:.1f}x baseline)")
    else:
        lines.append("- none detected")
    lines += [
        "",
        "## Recommended knobs",
        "",
        f"`--exaggeration {profile.recommended_knobs['exaggeration']} --cfg {profile.recommended_knobs['cfg']} --temperature {profile.recommended_knobs['temperature']}`",
        "",
        "## Transcript",
        "",
        profile.transcript,
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "audio",
        nargs="*",
        type=Path,
        default=[Path("~/Downloads/New Recording 63.m4a").expanduser()],
        help="One or more reference audio files (default: New Recording 63.m4a).",
    )
    args = parser.parse_args()
    audio_paths = [p.expanduser() for p in args.audio]

    for p in audio_paths:
        if not p.exists():
            print(f"Audio file not found: {p}", file=sys.stderr)
            raise SystemExit(1)

    profile = build_profile(audio_paths)

    style_dir = _double_chin_home() / "style"
    style_dir.mkdir(parents=True, exist_ok=True)
    json_path = style_dir / "profile.json"
    md_path = style_dir / "profile.md"

    json_path.write_text(json.dumps(profile.to_json(), indent=2) + "\n")
    md_path.write_text(render_markdown(profile))

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
