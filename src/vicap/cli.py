from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from vicap.config import get_settings
from vicap.core.db import get_session_maker
from vicap.domain.api_key_service import ApiKeyService
from vicap.pipeline import Pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def _async_create_key(name: str, rate_limit: int) -> None:
    maker = get_session_maker()
    async with maker() as db:
        svc = ApiKeyService(db)
        raw, key = await svc.create_key(name, rate_limit)
        print(f"API Key created:")
        print(f"  ID:      {key.id}")
        print(f"  Name:    {key.name}")
        print(f"  Key:     {raw}")
        print(f"  Hash:    {key.key_hash[:16]}...")
        print(f"  Limit:   {key.rate_limit} req/min")
        print(f"  Active:  {key.is_active}")
        print(f"  Store this key securely — it will not be shown again.")


async def _async_revoke_key(key_id: str) -> None:
    maker = get_session_maker()
    async with maker() as db:
        svc = ApiKeyService(db)
        ok = await svc.revoke_key(key_id)
        if ok:
            print(f"API Key {key_id} revoked.")
        else:
            print(f"API Key {key_id} not found.")


async def _async_list_keys() -> None:
    maker = get_session_maker()
    async with maker() as db:
        svc = ApiKeyService(db)
        keys = await svc.list_keys()
        if not keys:
            print("No API keys found.")
            return
        for k in keys:
            status = "active" if k.is_active else "revoked"
            print(
                f"  {k.id}  {k.name:<20} {status:<8} {k.rate_limit} req/min  created={k.created_at.date()}"
            )


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

    keys = sub.add_parser("keys", help="Manage API keys")
    keys_sub = keys.add_subparsers(dest="keys_command", required=True)

    keys_create = keys_sub.add_parser("create", help="Create a new API key")
    keys_create.add_argument("name", type=str, help="Human-readable name for the key")
    keys_create.add_argument(
        "--rate-limit", type=int, default=100, help="Requests per minute limit"
    )

    keys_revoke = keys_sub.add_parser("revoke", help="Revoke an API key")
    keys_revoke.add_argument("id", type=str, help="Key ID to revoke")

    keys_list = keys_sub.add_parser("list", help="List all API keys")

    args = parser.parse_args()

    if args.command == "keys":
        if args.keys_command == "create":
            asyncio.run(_async_create_key(args.name, args.rate_limit))
        elif args.keys_command == "revoke":
            asyncio.run(_async_revoke_key(args.id))
        elif args.keys_command == "list":
            asyncio.run(_async_list_keys())
        return

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
