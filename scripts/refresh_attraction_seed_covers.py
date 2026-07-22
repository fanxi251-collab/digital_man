#!/usr/bin/env python3
"""把仓库内 seed 封面同步到本机已有景点（无需清空 PostgreSQL attractions schema）。

适用：同事拉取了更新后的 src/lingjing_ai/assets/attractions/seed-*.webp，
但本地早已启动过，库里不是空库，默认不会重新播种。

用法（在项目根目录、已激活 Python 环境）：

    python scripts/refresh_attraction_seed_covers.py --workspace .
"""

from __future__ import annotations

import argparse
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lingjing_ai.services.attraction_store import AttractionStore, _demo_payloads, _seed_asset_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh attraction cover images from seed assets.")
    parser.add_argument("--workspace", type=Path, default=Path("."), help="Project workspace root.")
    args = parser.parse_args(argv)

    workspace = args.workspace.resolve()
    from lingjing_ai.config.settings import AppSettings

    settings = AppSettings.for_workspace(workspace)
    image_dir = workspace / "data" / "attraction_images"
    store = AttractionStore(
        settings.database_url,
        image_dir,
        seed_on_empty=False,
        schema=f"{settings.database_schema_prefix}attractions",
    )

    seed_dir = _seed_asset_dir()
    payloads = _demo_payloads()
    updated = 0

    for index, payload in enumerate(payloads, start=1):
        name = payload["name"]
        seed_name = f"seed-{index}.webp"
        source = seed_dir / seed_name
        if not source.is_file():
            print(f"skip {name}: missing {source}")
            continue

        matches = [item for item in store.list_attractions() if item.name == name]
        if not matches:
            print(f"skip {name}: attraction not found in local db")
            continue

        attraction = matches[0]
        # copy under a fresh runtime filename so browsers do not keep a stale cached cover
        runtime_name = f"cover-{uuid.uuid4().hex}.webp"
        target = image_dir / runtime_name
        shutil.copyfile(source, target)

        for old in attraction.images:
            if old.is_cover:
                store.delete_image(attraction.attraction_id, old.image_id)

        store.add_image(attraction.attraction_id, runtime_name, is_cover=True, sort_order=0)
        print(f"updated {name} -> /media/attractions/{runtime_name}")
        updated += 1

    if updated == 0:
        print("No covers updated. If the database is empty, just restart the server to auto-seed.")
        return 1
    print(f"Done. Refresh http://127.0.0.1:8000/visitor/explore ({updated} covers).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
