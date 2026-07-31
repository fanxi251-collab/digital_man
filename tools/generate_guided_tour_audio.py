from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
# The utility must run from a source checkout because competition machines may skip editable installation.
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from lingjing_ai.config.settings import AppSettings
from lingjing_ai.guided_tour.catalog import GuidedTourCatalog
from lingjing_ai.guided_tour.speech import GuidedTourSpeechService


async def generate(output_dir: Path, *, workspace: Path) -> None:
    settings = AppSettings.for_workspace(workspace)
    catalog = GuidedTourCatalog(workspace / "config" / "guided_tour.json")
    speech = GuidedTourSpeechService(
        enabled=settings.guided_tour_tts_enabled,
        subscription_key=settings.azure_speech_key,
        region=settings.azure_speech_region,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for stop in catalog.get_classic_route()["stops"]:
        filename = Path(stop["local_audio_url"]).name
        target = output_dir / filename
        # Each approved stop is written independently so reruns never delete or replace unrelated assets.
        audio = await speech.synthesize(stop["narration_text"])
        target.write_bytes(audio)
        print(f"generated {target.name} ({len(audio)} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate approved Xiaoxiao guided-tour MP3 files")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("frontend/public/digital-human/narration/xiaoxiao"),
    )
    args = parser.parse_args()
    workspace = WORKSPACE_ROOT
    output = args.output if args.output.is_absolute() else workspace / args.output
    asyncio.run(generate(output, workspace=workspace))


if __name__ == "__main__":
    main()
