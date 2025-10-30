import json
import re
from tqdm import tqdm

# --- Title cleaning helpers ---

def clean_title(raw_title: str) -> str:
    title = raw_title.lower().strip()

    # Remove common separators and metadata
    title = re.split(r"[\/\(\[\;]", title)[0]

    # Remove phrases like "by XYZ", "developed by", etc.
    title = re.sub(r"\b(by|developed by|written by|produced by|from)\b.*", "", title)

    # Remove trailing punctuation and extra spaces
    title = re.sub(r"[:\-]+$", "", title).strip()
    title = re.sub(r"\s{2,}", " ", title)
    title = title.strip(" :;-,")
    return title


def normalize_acronyms(title: str) -> str:
    # Insert space between letters and numbers (e.g. PES2017 → PES 2017)
    title = re.sub(r"([A-Za-z])(\d)", r"\1 \2", title)
    title = re.sub(r"(\d)([A-Za-z])", r"\1 \2", title)
    return title


def generate_title_variants(title: str):
    title = title.strip().lower()

    clean = clean_title(title)
    normalized = normalize_acronyms(clean)
    variants = [title.strip(), clean, normalized]

    # Try splitting on colon or dash — sometimes the second half is the real title
    parts = [p.strip() for p in re.split(r"[:\-]", title) if len(p.strip()) > 3]
    variants.extend(parts)

    # Deduplicate while preserving order
    seen = set()
    ordered = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            ordered.append(v)
    return ordered


# --- Main execution ---

def main(input_file="games.json", output_file="title_variants.json"):
    with open(input_file, "r", encoding="utf-8") as f:
        games = json.load(f)

    all_variants = []

    for game in tqdm(games, desc="Generating title variants"):
        dmc = game.get("dmc", {})
        raw_title = dmc.get("title", "").strip()

        variants = generate_title_variants(raw_title)
        all_variants.append({
            "id": dmc.get("id", ""),
            "raw_title": raw_title,
            "platform_id_guess": dmc.get("platform_id_guess", -1),
            "variants": variants
        })

    # Save results
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_variants, f, indent=2, ensure_ascii=False)

    print(f"\nTitle variants written to {output_file}")
    print("\nPreview of first few entries:")
    for sample in all_variants[:5]:
        print(json.dumps(sample, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

