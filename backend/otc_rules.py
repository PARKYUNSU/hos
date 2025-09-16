import json
from pathlib import Path
from typing import Dict, List, Tuple

RULES_PATH = Path(__file__).resolve().parent.parent / "data/otc_rules.json"


def load_rules() -> Dict:
    if not RULES_PATH.exists():
        return {"version": 0, "classes": {}, "products": [], "constraints": {}}
    with RULES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_rules(rules: Dict) -> None:
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RULES_PATH.open("w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def normalize_otc_list(otc_list: List[str], rules: Dict) -> List[str]:
    """Apply max_per_class, mutual exclusions, and avoid_pairs based on rules.
    Input otc_list is list of human-readable labels.
    """
    classes = rules.get("classes", {})
    constraints = rules.get("constraints", {})

    # Map label -> class via aliases
    def label_to_class(label: str) -> str:
        low = label.lower()
        for cname, info in classes.items():
            for alias in info.get("aliases", []):
                if alias.lower() in low:
                    return cname
        return "other"

    chosen: List[Tuple[str, str]] = []  # (label, class)
    per_class_count: Dict[str, int] = {}
    mutual_pairs = set(tuple(sorted(x)) for x in constraints.get("mutual_exclusions", []))

    for label in otc_list:
        cls = label_to_class(label)
        max_per = classes.get(cls, {}).get("max_per_recommendation", 1)
        if per_class_count.get(cls, 0) >= max_per:
            continue
        # mutual exclusion check
        conflict = False
        for _, c in chosen:
            if tuple(sorted((cls, c))) in mutual_pairs:
                conflict = True
                break
        if conflict:
            continue
        chosen.append((label, cls))
        per_class_count[cls] = per_class_count.get(cls, 0) + 1

    # avoid_pairs filtering (soft rule)
    avoid = set(tuple(sorted(x)) for x in constraints.get("avoid_pairs", []))
    final: List[str] = []
    for label, cls in chosen:
        bad = False
        for label2, cls2 in chosen:
            if label == label2:
                continue
            if tuple(sorted((cls, cls2))) in avoid:
                bad = True
                break
        if not bad:
            final.append(label)
    return final


