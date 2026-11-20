from pathlib import Path

EVAL_DIR = Path(__file__).parent / "data" / "eval"


def main() -> None:
    for txt in sorted(EVAL_DIR.glob("*.txt")):
        text = txt.read_text(encoding="utf-8")
        expected = txt.with_name(txt.stem + ".expected.json")
        status = "✓ expected.json" if expected.exists() else "✗ kein expected.json"
        print(f"{txt.name:35} {len(text):5} Zeichen   {status}")


if __name__ == "__main__":
    main()