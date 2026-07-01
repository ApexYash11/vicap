from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from vicap.config import get_settings
from vicap.pipeline import Pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="VICAP Studio CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    batch = sub.add_parser("batch", help="Batch process a video clip")
    batch.add_argument("path", type=Path, help="Path to video/audio file")
    batch.add_argument("--output", type=Path, help="Output JSON path")

    stream = sub.add_parser("stream", help="Stream process with SSE events")
    stream.add_argument("path", type=Path)

    clips = sub.add_parser("clips", help="Batch process all clips in data/clips/")
    clips.add_argument("--output-dir", type=Path)

    args = parser.parse_args()
    settings = get_settings()

    if not settings.has_api_key:
        logging.error("Set FIREWORKS_API_KEY in .env")
        raise SystemExit(1)

    pipeline = Pipeline()

    if args.command == "batch":
        memory = asyncio.run(pipeline.process_batch(args.path))
        print(json.dumps(memory.to_dict(), indent=2))
        if args.output:
            args.output.write_text(json.dumps(memory.to_dict(), indent=2), encoding="utf-8")

    elif args.command == "stream":

        async def run_stream():
            async for event in pipeline.stream_session(args.path):
                print(json.dumps(event))

        asyncio.run(run_stream())

    elif args.command == "clips":
        settings.clips_dir.mkdir(parents=True, exist_ok=True)
        out_dir = args.output_dir or settings.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        async def run_all():
            for clip in sorted(settings.clips_dir.iterdir()):
                if not clip.is_file():
                    continue
                logging.info("Processing %s", clip.name)
                memory = await pipeline.process_batch(clip)
                out = out_dir / f"{clip.stem}_captions.json"
                out.write_text(json.dumps(memory.to_dict(), indent=2), encoding="utf-8")
                logging.info("Wrote %s", out)

        asyncio.run(run_all())


if __name__ == "__main__":
    main()
