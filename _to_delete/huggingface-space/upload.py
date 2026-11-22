"""Puts the online version together and uploads it to the Hugging Face Space (run by .github/workflows/space.yml).

Only what the app needs goes online: the code and the fictional example letters.
The upload goes through Hugging Face's API, which stores images and PDFs the way the Hub requires.
"""

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
EXAMPLES = ["data/photos", "data/eval/krankenkasse_02.txt"]


def build(target: Path) -> Path:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in ["LICENSE"]:
        shutil.copy(ROOT / name, target / name)
    shutil.copytree(ROOT / "src", target / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for example in EXAMPLES:
        source, dest = ROOT / example, target / example
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():   # *.ocr.txt: transcriptions the app saves next to a photo, not part of the examples
            shutil.copytree(source, dest, ignore=shutil.ignore_patterns("*.ocr.txt"))
        else:
            shutil.copy(source, dest)
    for name in ["app.py", "requirements.txt", "README.md"]:      # README.md here is the Space's own page
        shutil.copy(HERE / name, target / name)
    return target


def upload(folder: Path, space: str, token: str, message: str) -> None:
    from huggingface_hub import HfApi

    # delete_patterns: files that are gone from the project also disappear from the Space
    HfApi(token=token).upload_folder(repo_id=space, repo_type="space", folder_path=str(folder),
                                     commit_message=message, delete_patterns=["src/**", "data/**"])


if __name__ == "__main__":
    folder = build(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "build" / "space"))
    if os.environ.get("HF_TOKEN") and os.environ.get("HF_SPACE"):
        message = (os.environ.get("COMMIT_MESSAGE") or "Update").splitlines()[0][:120]
        upload(folder, os.environ["HF_SPACE"], os.environ["HF_TOKEN"], message)
        print(f"Uploaded to https://huggingface.co/spaces/{os.environ['HF_SPACE']}")
    else:
        print(f"Built {folder} (set HF_TOKEN and HF_SPACE to upload)")
