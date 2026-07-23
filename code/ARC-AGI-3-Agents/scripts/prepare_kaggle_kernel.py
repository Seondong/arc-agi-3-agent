"""[Mar 29] Created by SD with GPT-5.4.

Prepare a Kaggle notebook bundle with kernel-metadata.json for ARC-AGI-3.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--notebook",
        type=Path,
        default=REPO_ROOT / "kaggle_submission.ipynb",
        help="Source notebook to include in the bundle.",
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=AGENTS_ROOT / "artifacts" / "kaggle_kernel_bundle",
        help="Output directory for kaggle kernels push.",
    )
    parser.add_argument(
        "--owner",
        default="sundong",
        help="Kaggle username/owner.",
    )
    parser.add_argument(
        "--slug",
        default="arc-agi-3-hybrid-stage1b",
        help="Notebook slug to push under the Kaggle account.",
    )
    parser.add_argument(
        "--title",
        default="ARC AGI 3 Hybrid Stage1b",
        help="Notebook title. It should roughly slugify to the notebook slug.",
    )
    args = parser.parse_args()

    notebook_path = args.notebook.resolve()
    if not notebook_path.exists():
        raise SystemExit(f"Notebook not found: {notebook_path}")

    bundle_dir = args.bundle_dir.resolve()
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    notebook_dst = bundle_dir / notebook_path.name
    shutil.copy2(notebook_path, notebook_dst)

    metadata = {
        "id": f"{args.owner}/{args.slug}",
        "title": args.title,
        "code_file": notebook_dst.name,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": False,
        "competition_sources": ["arc-prize-2026-arc-agi-3"],
        "dataset_sources": [
            f"{args.owner}/qwen3-5-0-8b",
            f"{args.owner}/qwen35-sft-adapter",
            f"{args.owner}/small-policy-prior",
        ],
    }
    write_json(bundle_dir / "kernel-metadata.json", metadata)

    manifest = {
        "bundle_dir": str(bundle_dir),
        "notebook": str(notebook_dst),
        "kernel_metadata": str(bundle_dir / "kernel-metadata.json"),
        "kernel_id": metadata["id"],
    }
    write_json(bundle_dir / "bundle-manifest.json", manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
