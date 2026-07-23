"""[Mar 29] Created by SD with GPT-5.4.

Prepare upload-ready Kaggle asset directories for the current best adapter.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def write_dataset_metadata(path: Path, dataset_id: str, title: str) -> None:
    payload = {
        "title": title,
        "id": dataset_id,
        "licenses": [{"name": "CC0-1.0"}],
    }
    (path / "dataset-metadata.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=REPO_ROOT / "artifacts",
    )
    parser.add_argument(
        "--adapter-name",
        default="qwen35_sft_adapter_stage1b_mps",
        help="Source adapter directory inside artifacts/.",
    )
    parser.add_argument(
        "--kaggle-owner",
        default="sundong",
        help="Kaggle username/owner for dataset metadata.",
    )
    parser.add_argument(
        "--include-base-model",
        action="store_true",
        help="Copy the local Qwen3.5-0.8B cache into the upload tree as qwen3-5-0-8b.",
    )
    args = parser.parse_args()

    artifacts_dir = args.artifacts_dir.resolve()
    adapter_src = artifacts_dir / args.adapter_name
    if not adapter_src.exists():
        raise SystemExit(f"Adapter source not found: {adapter_src}")

    prior_src = artifacts_dir / "small_policy_prior.pt"
    if not prior_src.exists():
        raise SystemExit(f"Prior not found: {prior_src}")

    upload_dir = artifacts_dir / "kaggle_upload"
    adapter_dst = upload_dir / "qwen35-sft-adapter"
    copy_tree(adapter_src, adapter_dst)
    write_dataset_metadata(
        adapter_dst,
        f"{args.kaggle_owner}/qwen35-sft-adapter",
        "qwen35-sft-adapter",
    )

    prior_dst_dir = upload_dir / "small-policy-prior"
    legacy_prior = upload_dir / "small_policy_prior.pt"
    if legacy_prior.exists():
        legacy_prior.unlink()
    if prior_dst_dir.exists():
        shutil.rmtree(prior_dst_dir)
    prior_dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(prior_src, prior_dst_dir / "small_policy_prior.pt")
    write_dataset_metadata(
        prior_dst_dir,
        f"{args.kaggle_owner}/small-policy-prior",
        "small-policy-prior",
    )

    base_model_cache = Path(
        "/Users/sundong/.cache/huggingface/hub/models--Qwen--Qwen3.5-0.8B/"
        "snapshots/2fc06364715b967f1860aea9cf38778875588b17"
    )
    if args.include_base_model:
        base_dst = upload_dir / "qwen3-5-0-8b"
        base_dst.mkdir(parents=True, exist_ok=True)
        copy_tree(base_model_cache, base_dst)
        write_dataset_metadata(
            base_dst,
            f"{args.kaggle_owner}/qwen3-5-0-8b",
            "qwen3-5-0-8b",
        )

    manifest = {
        "recommended_adapter": args.adapter_name,
        "adapter_upload_dir": str(adapter_dst),
        "prior_upload_dir": str(prior_dst_dir),
        "base_model_cache": str(base_model_cache),
        "base_model_upload_dir": str(upload_dir / "qwen3-5-0-8b") if args.include_base_model else None,
    }
    (upload_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
