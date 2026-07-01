from __future__ import annotations

import base64
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from vicap.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class VideoChunk:
    chunk_id: int
    start_sec: float
    end_sec: float
    video_path: Path
    video_b64: str
    is_static: bool = False


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")


def preprocess_chunk(input_path: Path, start: float, duration: float, out_path: Path) -> None:
    settings = get_settings()
    cfg = __import__("vicap.config", fromlist=["load_models_config"]).load_models_config()
    preprocess = cfg.get("preprocess", {})
    fps = preprocess.get("fps", 1)
    height = preprocess.get("height", 360)

    _run_ffmpeg(
        [
            "-ss",
            str(start),
            "-i",
            str(input_path),
            "-t",
            str(duration),
            "-vf",
            f"fps={fps},scale=-1:{height}",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-an",
            str(out_path),
        ]
    )


def mux_audio_for_conference(audio_path: Path, out_path: Path, duration: float) -> None:
    """Create minimal MP4 (black frame + audio) for Kimi when input is audio-only."""
    _run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=640x360:d={duration}",
            "-i",
            str(audio_path),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(out_path),
        ]
    )


def normalize_media(input_path: Path, out_path: Path, max_duration: float | None = None) -> None:
    cfg = __import__("vicap.config", fromlist=["load_models_config"]).load_models_config()
    preprocess = cfg.get("preprocess", {})
    fps = preprocess.get("fps", 1)
    height = preprocess.get("height", 360)
    max_d = max_duration or preprocess.get("max_duration_sec", 60)

    args = [
        "-i",
        str(input_path),
        "-t",
        str(max_d),
        "-vf",
        f"fps={fps},scale=-1:{height}",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
    ]
    suffix = input_path.suffix.lower()
    if suffix in {".mp3", ".wav", ".ogg", ".m4a", ".opus"}:
        mux_audio_for_conference(input_path, out_path, max_d)
        return

    args.extend(["-c:a", "aac", "-b:a", "64k", str(out_path)])
    _run_ffmpeg(args)


def get_video_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 60.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 60.0


def frame_diff_ratio(path_a: Path, path_b: Path) -> float:
    """Estimate motion between two chunks via ffmpeg signalstats (fallback: always change)."""
    try:
        for p in (path_a, path_b):
            if not p.exists() or p.stat().st_size == 0:
                return 1.0

        def extract_frame(video: Path, frame_path: Path) -> None:
            _run_ffmpeg(["-i", str(video), "-vframes", "1", str(frame_path)])

        with tempfile.TemporaryDirectory() as tmp:
            fa = Path(tmp) / "a.png"
            fb = Path(tmp) / "b.png"
            extract_frame(path_a, fa)
            extract_frame(path_b, fb)
            if not fa.exists() or not fb.exists():
                return 1.0
            # Simple byte diff ratio as proxy
            ba, bb = fa.read_bytes(), fb.read_bytes()
            if len(ba) == 0 or len(bb) == 0:
                return 1.0
            min_len = min(len(ba), len(bb))
            diff = sum(1 for i in range(min_len) if ba[i] != bb[i]) / min_len
            return diff
    except Exception as exc:
        logger.debug("frame_diff_ratio fallback: %s", exc)
        return 1.0


def encode_video_b64(path: Path) -> str:
    cfg = __import__("vicap.config", fromlist=["load_models_config"]).load_models_config()
    max_bytes = cfg.get("preprocess", {}).get("max_payload_bytes", 10_485_760)
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"Chunk payload {len(data)} exceeds max {max_bytes} bytes")
    return base64.b64encode(data).decode("utf-8")


def chunk_video(input_path: Path) -> list[VideoChunk]:
    settings = get_settings()
    duration = get_video_duration(input_path)
    chunk_dur = settings.chunk_duration_sec
    overlap = settings.chunk_overlap_sec
    step = max(chunk_dur - overlap, 0.5)

    chunks: list[VideoChunk] = []
    prev_chunk_path: Path | None = None

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        start = 0.0
        chunk_id = 0

        while start < duration:
            end = min(start + chunk_dur, duration)
            actual_dur = end - start
            if actual_dur < 0.3:
                break

            chunk_file = tmp_path / f"chunk_{chunk_id:04d}.mp4"
            preprocess_chunk(input_path, start, actual_dur, chunk_file)

            is_static = False
            if prev_chunk_path is not None:
                diff = frame_diff_ratio(prev_chunk_path, chunk_file)
                is_static = diff < settings.motion_gate_threshold

            if not is_static:
                b64 = encode_video_b64(chunk_file)
            else:
                b64 = ""

            chunks.append(
                VideoChunk(
                    chunk_id=chunk_id,
                    start_sec=start,
                    end_sec=end,
                    video_path=chunk_file,
                    video_b64=b64,
                    is_static=is_static,
                )
            )
            prev_chunk_path = chunk_file
            chunk_id += 1
            start += step

    return chunks
