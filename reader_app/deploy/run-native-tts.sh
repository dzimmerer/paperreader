#!/usr/bin/env bash
# Run the Kokoro TTS server NATIVELY on the macOS host (port 5102).
#
# Why: PyTorch CPU inference inside minikube's Linux VM on Apple Silicon is
# ~7x slower than native (no Apple Accelerate/AMX) — about 0.6x realtime, which
# causes a pause before every sentence. Running natively here gives ~4.7x
# realtime (RTF ~0.21), so playback never waits.
#
# Pair with deploy/k8s/tts-native.yaml (ExternalName service) so the in-cluster backend
# reaches this process via http://tts:5102 -> host.minikube.internal:5102.
set -euo pipefail

cd "$(dirname "$0")/../.."  # repo root (KokoroInterface loads kokoro/ from here)

# Prefer the project's conda env; fall back to whatever python is on PATH.
PY="${PYTHON:-/opt/homebrew/Caskroom/miniforge/base/envs/paperreader/bin/python}"
[ -x "$PY" ] || PY="python3"

export TTS_ENGINE="${TTS_ENGINE:-kokoro}"
export TTS_VOICE="${TTS_VOICE:-af_sarah}"
export TTS_DEVICE="${TTS_DEVICE:-cpu}"   # CPU+Accelerate beats MPS for Kokoro
export TTS_PORT="${TTS_PORT:-5102}"

echo "Starting native $TTS_ENGINE TTS (voice=$TTS_VOICE, device=$TTS_DEVICE) on :$TTS_PORT"
echo "Using python: $PY"
exec "$PY" reader_app/tts_server.py
