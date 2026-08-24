#!/usr/bin/env python3
"""
Fetch the XRepoTest benchmark data from the HuggingFace Hub into the local paths
the pipeline expects.

This is the "setup step 0" for running evaluation from a fresh clone. It downloads
the published dataset from a single HF dataset repo and places each artifact where
`xrepotest` looks for it:

    HF data/<folder>/<file>            ->  local target
    ------------------------------------------ ------------------------------- ----------
    data/base/<lang>_functions.jsonl                 src/xrepotest/environments/xrepotest/  (standard / file_context)
    data/lsp/<lang>_functions_enriched.jsonl         data/enriched/lsp/                     (lsp_context)
    data/rag/<lang>_...ws.._k20_enriched_*.jsonl     data/enriched/rag/                     (rag_bm25 / rag_dense)

`repo_data/` is intentionally NOT fetched; it is only needed to rebuild the dataset
or the evaluation Docker images from scratch.

Usage:
    python scripts/fetch_data.py [--repo solis-soict/xrepotest] [--lang go] [--group all]
    python scripts/fetch_data.py --group base          # only core task items
    python scripts/fetch_data.py --lang rust           # only rust files across all groups

Public datasets do not require a token.
"""

import argparse
import os
import sys
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

ROOT = Path(__file__).resolve().parents[1]

# Local destination roots (resolved via the same layout the code expects).
BASE_DST = ROOT / "src" / "xrepotest" / "environments" / "xrepotest"
LSP_DST = ROOT / "data" / "enriched" / "lsp"
RAG_DST = ROOT / "data" / "enriched" / "rag"

REMOTE_TO_DST = [
    ("base", "data/base", BASE_DST),
    ("lsp", "data/lsp", LSP_DST),
    ("rag", "data/rag", RAG_DST),
]

LANGS = ("go", "rust", "julia", "php", "ruby")


def fetch_group(api: HfApi, repo: str, group: str, remote_dir: str, dst: Path,
                lang: str | None, force: bool) -> list[str]:
    files = api.list_repo_files(repo_id=repo, repo_type="dataset")
    remote_dir = remote_dir + "/"
    candidates = [f for f in files if f.startswith(remote_dir) and f.endswith(".jsonl")]
    candidates = [f for f in candidates if Path(f).name not in ("config.json",)]
    if lang:
        candidates = [f for f in candidates if f.split("/")[-1].startswith(f"{lang}_")]

    fetched = []
    for remote_path in sorted(candidates):
        name = remote_path.split("/")[-1]
        dst.mkdir(parents=True, exist_ok=True)
        target = dst / name
        if target.exists() and not force:
            print(f"  · {name:60s} exists, skipping (--force to overwrite)")
            continue
        print(f"  ⤓ {remote_path}")
        # hf_hub_download caches to ~/.cache/huggingface; we then copy to dst so
        # the pipeline finds the file at the canonical location.
        cached = hf_hub_download(repo_id=repo, repo_type="dataset", filename=remote_path)
        shutil_copy(cached, target)
        fetched.append(name)
    return fetched


def shutil_copy(src: str, dst: Path) -> None:
    import shutil
    shutil.copy(src, dst)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=os.environ.get("XREPOTEST_HF_REPO", "solis-soict/xrepotest"),
                    help="HF dataset repo id (default: solis-soict/xrepotest or $XREPOTEST_HF_REPO)")
    ap.add_argument("--group", choices=["base", "lsp", "rag", "all"], default="all")
    ap.add_argument("--lang", choices=LANGS, default=None, help="Fetch only one language")
    ap.add_argument("--force", action="store_true", help="Overwrite existing local files")
    args = ap.parse_args()

    print(f"Fetching XRepoTest data from: {args.repo}")
    print(f"  (set XREPOTEST_HF_REPO to point at a different mirror)\n")

    api = HfApi(token=os.environ.get("HF_TOKEN", None))

    groups = REMOTE_TO_DST if args.group == "all" else [g for g in REMOTE_TO_DST if g[0] == args.group]
    if not groups:
        raise SystemExit(f"Unknown group: {args.group}")

    n = 0
    for group, remote_dir, dst in groups:
        print(f"[{group}] -> {dst.relative_to(ROOT)}")
        n += len(fetch_group(api, args.repo, group, remote_dir, dst, args.lang, args.force))
        print()

    print(f"Done. {n} file(s) placed. Next: `xrepotest run ...`")
    print("Note: repo_data/ is not downloaded (only needed to rebuild the dataset/Docker images).")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)