#!/usr/bin/env bash
# Assemble demo/myna-demo.mp4 and demo/myna-walkthrough.mp4 from PNG slides
# (demo/video/slides/*.png) and audio (demo asset wavs + narration wavs).
#
# Requires: /opt/homebrew/bin/ffmpeg, /opt/homebrew/bin/ffprobe (the
# /usr/local ffmpeg on this machine is a broken x86_64 build).
#
# Usage: bash demo/video/build_videos.sh
set -euo pipefail

FFMPEG=/opt/homebrew/bin/ffmpeg
FFPROBE=/opt/homebrew/bin/ffprobe

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SLIDES_DIR="$SCRIPT_DIR/slides"
NARRATION_DIR="$SCRIPT_DIR/narration"
ASSETS_DIR="$REPO_ROOT/demo/assets"
BUILD_DIR="$SCRIPT_DIR/build"
DEMO_OUT="$REPO_ROOT/demo/myna-demo.mp4"
WALK_OUT="$REPO_ROOT/demo/myna-walkthrough.mp4"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Uniform encoding target.
FPS=30
W=1920
H=1080
VCODEC=(-c:v libx264 -crf 20 -pix_fmt yuv420p -r "$FPS")
ACODEC=(-c:a aac -b:a 128k -ar 24000 -ac 1)
FASTSTART=(-movflags +faststart)
FADE_DUR=0.5

duration_of() {
  "$FFPROBE" -v error -show_entries format=duration -of default=nw=1:nk=1 "$1"
}

# ---------------------------------------------------------------------------
# Segment builders
# ---------------------------------------------------------------------------

# silent_segment IMAGE DURATION OUT
silent_segment() {
  local image="$1" dur="$2" out="$3"
  "$FFMPEG" -y -loop 1 -t "$dur" -i "$image" \
    -f lavfi -t "$dur" -i "anullsrc=r=24000:cl=mono" \
    -vf "scale=${W}:${H},fps=${FPS},format=yuv420p" \
    "${VCODEC[@]}" "${ACODEC[@]}" "${FASTSTART[@]}" \
    -shortest "$out"
}

# audio_segment IMAGE AUDIO DURATION OUT   (audio trimmed/used as-is to DURATION)
audio_segment() {
  local image="$1" audio="$2" dur="$3" out="$4"
  "$FFMPEG" -y -loop 1 -t "$dur" -i "$image" \
    -t "$dur" -i "$audio" \
    -vf "scale=${W}:${H},fps=${FPS},format=yuv420p" \
    "${VCODEC[@]}" "${ACODEC[@]}" "${FASTSTART[@]}" \
    -shortest "$out"
}

# padded_audio_segment IMAGE AUDIO TAIL_PAD OUT  (video length = audio + pad)
padded_audio_segment() {
  local image="$1" audio="$2" pad="$3" out="$4"
  local adur total
  adur=$(duration_of "$audio")
  total=$(python3 -c "print(float('$adur') + float('$pad'))")
  "$FFMPEG" -y -loop 1 -t "$total" -i "$image" \
    -i "$audio" \
    -filter_complex "[1:a]apad=pad_dur=${pad}[aout]" \
    -map 0:v -map "[aout]" \
    -vf "scale=${W}:${H},fps=${FPS},format=yuv420p" \
    "${VCODEC[@]}" "${ACODEC[@]}" "${FASTSTART[@]}" \
    -t "$total" "$out"
}

# ---------------------------------------------------------------------------
# DEMO segments
# ---------------------------------------------------------------------------
echo "== building demo segments =="

silent_segment "$SLIDES_DIR/d1.png" 3.5 "$BUILD_DIR/seg_d1.mp4"

audio_segment "$SLIDES_DIR/d2.png" "$ASSETS_DIR/standin_reference.wav" 8 "$BUILD_DIR/seg_d2.mp4"

silent_segment "$SLIDES_DIR/d3.png" 5 "$BUILD_DIR/seg_d3.mp4"

silent_segment "$SLIDES_DIR/d4.png" 4 "$BUILD_DIR/seg_d4.mp4"

# d5: full demo-clone.wav with a live waveform overlaid on the lower half.
CLONE_WAV="$REPO_ROOT/demo/demo-clone.wav"
CLONE_DUR=$(duration_of "$CLONE_WAV")
"$FFMPEG" -y -loop 1 -t "$CLONE_DUR" -i "$SLIDES_DIR/d5.png" \
  -i "$CLONE_WAV" \
  -filter_complex "[0:v]scale=${W}:${H},fps=${FPS},format=yuv420p[bg];[1:a]showwaves=s=1680x360:mode=cline:colors=0xe2e8f0:rate=${FPS}[wave];[bg][wave]overlay=x=120:y=620:shortest=1[outv]" \
  -map "[outv]" -map 1:a \
  "${VCODEC[@]}" "${ACODEC[@]}" "${FASTSTART[@]}" \
  -t "$CLONE_DUR" "$BUILD_DIR/seg_d5.mp4"

silent_segment "$SLIDES_DIR/d6.png" 5.5 "$BUILD_DIR/seg_d6.mp4"

# Concat demo segments (re-encoded, so concat demuxer stream copy is safe: all
# segments already share codec/params).
cat > "$BUILD_DIR/demo_concat.txt" <<EOF
file 'seg_d1.mp4'
file 'seg_d2.mp4'
file 'seg_d3.mp4'
file 'seg_d4.mp4'
file 'seg_d5.mp4'
file 'seg_d6.mp4'
EOF
"$FFMPEG" -y -f concat -safe 0 -i "$BUILD_DIR/demo_concat.txt" -c copy "$BUILD_DIR/demo_raw.mp4"

DEMO_TOTAL=$(duration_of "$BUILD_DIR/demo_raw.mp4")
DEMO_FADE_OUT_ST=$(python3 -c "print(max(0.0, float('$DEMO_TOTAL') - $FADE_DUR))")

"$FFMPEG" -y -i "$BUILD_DIR/demo_raw.mp4" \
  -vf "fade=t=in:st=0:d=${FADE_DUR},fade=t=out:st=${DEMO_FADE_OUT_ST}:d=${FADE_DUR}" \
  -af "afade=t=in:st=0:d=${FADE_DUR},afade=t=out:st=${DEMO_FADE_OUT_ST}:d=${FADE_DUR}" \
  "${VCODEC[@]}" "${ACODEC[@]}" "${FASTSTART[@]}" \
  "$DEMO_OUT"

echo "wrote $DEMO_OUT (duration ${DEMO_TOTAL}s)"

# ---------------------------------------------------------------------------
# WALKTHROUGH segments
# ---------------------------------------------------------------------------
echo "== building walkthrough segments =="

TAIL_PAD=0.7
for n in 1 2 3 4 5 6 7 8; do
  padded_audio_segment "$SLIDES_DIR/w${n}.png" "$NARRATION_DIR/w${n}.wav" "$TAIL_PAD" "$BUILD_DIR/seg_w${n}.mp4"
done

cat > "$BUILD_DIR/walk_concat.txt" <<EOF
file 'seg_w1.mp4'
file 'seg_w2.mp4'
file 'seg_w3.mp4'
file 'seg_w4.mp4'
file 'seg_w5.mp4'
file 'seg_w6.mp4'
file 'seg_w7.mp4'
file 'seg_w8.mp4'
EOF
"$FFMPEG" -y -f concat -safe 0 -i "$BUILD_DIR/walk_concat.txt" -c copy "$BUILD_DIR/walk_raw.mp4"

WALK_TOTAL=$(duration_of "$BUILD_DIR/walk_raw.mp4")
WALK_FADE_OUT_ST=$(python3 -c "print(max(0.0, float('$WALK_TOTAL') - $FADE_DUR))")

"$FFMPEG" -y -i "$BUILD_DIR/walk_raw.mp4" \
  -vf "fade=t=in:st=0:d=${FADE_DUR},fade=t=out:st=${WALK_FADE_OUT_ST}:d=${FADE_DUR}" \
  -af "afade=t=in:st=0:d=${FADE_DUR},afade=t=out:st=${WALK_FADE_OUT_ST}:d=${FADE_DUR}" \
  "${VCODEC[@]}" "${ACODEC[@]}" "${FASTSTART[@]}" \
  "$WALK_OUT"

echo "wrote $WALK_OUT (duration ${WALK_TOTAL}s)"
