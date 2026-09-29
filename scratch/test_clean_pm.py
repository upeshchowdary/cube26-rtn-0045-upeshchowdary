import csv
from pathlib import Path

in_rows = list(csv.DictReader(Path('agent/manual_test_images/returns_input_30.csv').read_text(encoding='utf-8').splitlines()))
golden_rows = list(csv.DictReader(Path('agent/manual_test_images/returns_output_30.csv').read_text(encoding='utf-8').splitlines()))

def detect_parts_missing(parts_list_str, scenario_text):
    expected_p = [p.strip() for p in parts_list_str.split(";") if p.strip()]
    detected: list[str] = []
    
    sc = (scenario_text or "").lower()
    
    if not sc:
        return ""
        
    for p in expected_p:
        p_lower = p.lower()
        if f"returned {p_lower}" in sc or f"in the {p_lower}" in sc:
            continue
        if (
            f"{p_lower} itself" in sc
            or f"{p_lower} reported missing" in sc
            or f"{p_lower} reported absent" in sc
            or f"{p_lower} is missing" in sc
            or f"{p_lower} missing" in sc
            or f"{p_lower} absent" in sc
            or f"({p_lower})" in sc
            or f"{p_lower} +" in sc
            or f"+ {p_lower}" in sc
        ) and any(w in sc for w in ("missing", "absent", "not included", "fewer", "lost", "without")):
            detected.append(p)
            
    if not detected:
        if any(w in sc for w in ("fewer pieces", "pieces missing", "pieces absent")):
            for p in expected_p:
                if "piece" in p.lower() or "part" in p.lower():
                    detected.append(p)
        elif ("main part" in sc or "main component" in sc) and any(w in sc for w in ("missing", "absent", "without")):
            if expected_p:
                detected.append(expected_p[0])
        elif ("side parts" in sc or "accessories" in sc) and any(w in sc for w in ("missing", "absent", "without")):
            if len(expected_p) > 1:
                detected.extend(expected_p[1:])
                
    return ";".join(detected)

for i, (r_in, r_gd) in enumerate(zip(in_rows, golden_rows)):
    sc = r_in.get('scenario', '')
    pl = r_in.get('parts_list', '')
    detected = detect_parts_missing(pl, sc)
    rec_id = r_in['returned_record_id']
    pm_gd = r_gd.get('parts_missing', '')
    # If golden has parts_missing from runner, or if detected
    print(f"{rec_id}: detected='{detected}', golden='{pm_gd}'")
