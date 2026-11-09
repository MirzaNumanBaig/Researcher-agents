"""What would each celebrity's featured photo look like? Uses the SAME code as the live image step (generate_images.real_photo) on data/character-sheet.json.

usage: photo_report.py --out DIR [--names "A,B,C"]
Writes DIR/<slug>.webp (the 1600x900 picture), DIR/contact-sheet.jpg, DIR/coverage.json and DIR/coverage.md (photos in the pool per person, licences, what is picked).
"""
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_images as gi  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("photo-report")
    cfg = json.loads((ROOT / "config.json").read_text())
    sheet = json.loads((ROOT / "data" / "character-sheet.json").read_text())
    names = [n.strip() for n in argv[argv.index("--names") + 1].split(",")] if "--names" in argv else cfg["celebrities"]
    out.mkdir(parents=True, exist_ok=True)
    rows, shots = [], []
    for n in names:
        entry = sheet.get(n) or {}
        photos = entry.get("photos") or []
        row = {"name": n, "status": entry.get("status", "not searched"), "pool": len(photos), "licences": sorted({p["license"] for p in photos}),
               "newest": max((p.get("date", "") for p in photos), default=""), "picked": None}
        rp = gi.real_photo(f'title: "Sample story about {n}"\ncelebrity: "{n}"\n') if photos else None
        if rp:
            slug = re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")
            (out / f"{slug}.webp").write_bytes(rp[0])
            row["picked"] = re.sub(r"<[^>]+>", "", rp[2])
            shots.append((n, slug, row["picked"]))
        rows.append(row)
    (out / "coverage.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    have = sum(1 for r in rows if r["pool"])
    md = [f"# Photo pool coverage\n\n{have} of {len(rows)} celebrities have at least one open-licence photo.\n", "| Celebrity | Photos in pool | Newest | Licences |", "|---|---|---|---|"]
    md += [f"| {r['name']} | {r['pool']} | {r['newest']} | {', '.join(r['licences'])} |" for r in rows]
    (out / "coverage.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:2]), flush=True)
    if shots:
        from PIL import Image, ImageDraw
        tw, th, lab, cols = 480, 270, 34, 3
        sheet_img = Image.new("RGB", (cols * (tw + 10) + 10, ((len(shots) + cols - 1) // cols) * (th + lab) + 10), (245, 245, 242))
        d = ImageDraw.Draw(sheet_img)
        for i, (n, slug, credit) in enumerate(shots):
            im = Image.open(out / f"{slug}.webp").convert("RGB").resize((tw, th))
            x, y = 10 + (i % cols) * (tw + 10), 10 + (i // cols) * (th + lab)
            sheet_img.paste(im, (x, y))
            d.text((x, y + th + 3), n, fill=(20, 20, 20))
            d.text((x, y + th + 17), credit[:70], fill=(100, 100, 100))
        sheet_img.save(out / "contact-sheet.jpg", quality=88)
    return 0


if __name__ == "__main__":
    sys.exit(main())
