"""Subset the OFL-licensed font for the UI/manual; requires fonttools[woff]."""
from pathlib import Path
import argparse
from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--family", choices=("sans", "serif"), default="sans")
args = parser.parse_args()
source_name = "NotoSansSC.ttf" if args.family == "sans" else "NotoSerifSC.ttf"
source = ROOT / "output/font-source" / source_name
characters = set(chr(n) for n in range(32, 127))
for folder in ("app", "static", "reference"):
    for path in (ROOT / folder).rglob("*"):
        if path.is_file() and path.suffix in {".py", ".js", ".html", ".md"}:
            characters.update(path.read_text(encoding="utf-8"))
characters.update("✓×←→−＋≤≥%·–…")
font = TTFont(source)
options = subset.Options()
options.flavor = "woff2"
options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]
options.name_legacy = True
subsetter = subset.Subsetter(options=options)
subsetter.populate(text="".join(sorted(characters)))
subsetter.subset(font)
font.flavor = "woff2"
output = ROOT / f"static/fonts/ccm-ui-{args.family}.woff2"
font.save(output)
print(f"Subset font: {output.stat().st_size} bytes; {len(characters)} codepoints requested")
