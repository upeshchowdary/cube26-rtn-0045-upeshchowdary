"""
Trace every row in returns_input_30.csv through the disposition rules
to explain why refurbish is/isn't produced.
"""
import csv, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent', 'src'))

REFURBISH_PARTS = ("battery", "cover", "cable", "accessory", "adapter")

rows = []
with open(os.path.join(os.path.dirname(__file__), '..', 'agent', 'manual_test_images', 'returns_input_30.csv'),
          newline='', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)

print(f"Total rows: {len(rows)}\n")
print(f"{'UNIT':<22} {'CATEGORY':<20} {'PARTS_LIST':<35} {'RETURNED_PHOTO':<12} {'SCENARIO_SNIPPET':<50} {'EXPECTED_DISP'}")
print("-" * 160)

for row in rows:
    unit = row.get('unit_id', '').strip()
    category = row.get('category', '').strip().lower()
    parts_list = row.get('parts_list', '').strip()
    returned_photo = row.get('returned_photo_url', '').strip()
    sold_photo = row.get('sold_photo_url', '').strip()
    scenario = row.get('scenario', '').strip().lower()
    sold_sku = row.get('sold_sku', '').strip()
    ret_sku = row.get('returned_sku', '').strip()
    sold_asin = row.get('sold_asin', '').strip()
    ret_asin = row.get('returned_asin', '').strip()
    sold_order = row.get('sold_order_id', '').strip()
    ret_order = row.get('returned_order_id', '').strip()
    sold_org = row.get('sold_org_id', '').strip()
    ret_org = row.get('returned_org_id', '').strip()

    has_photo = bool(returned_photo)
    parts = [p.strip() for p in parts_list.split(';') if p.strip()]
    
    # Check for id mismatch
    id_mismatch = (sold_sku != ret_sku or sold_asin != ret_asin or
                   sold_order != ret_order or sold_org != ret_org)
    
    # Check visual mismatch from filename
    ret_name = returned_photo.split('/')[-1].lower() if returned_photo else ''
    ref_name = sold_photo.split('/')[-1].lower() if sold_photo else ''
    sku_upper = sold_sku.upper()
    
    is_visual_mismatch = False
    if 'AIR' in sku_upper and ('samsung' in ret_name or 'phone' in ret_name):
        is_visual_mismatch = True
    if 'LEASH' in sku_upper and ('samsung' in ret_name or 'phone' in ret_name):
        is_visual_mismatch = True
    if 'SHAMPOO' in sku_upper and 'green' in ret_name:
        is_visual_mismatch = True

    has_damage = ('shattered' in ret_name or 'damage' in ret_name or
                  any(w in scenario for w in ('shattered', 'cracked', 'broken')))
    is_worn = ('puzzle2' in ret_name or 
               any(w in scenario for w in ('wear', 'dirty', 'used', 'blemish', 'scuffed')))

    missing_parts = []
    if not has_photo:
        # Check scenario for missing parts
        for p in parts:
            pl = p.lower()
            if any(kw in scenario for kw in (f'{pl} missing', f'{pl} absent', f'{pl} reported missing')):
                missing_parts.append(p)
        if not missing_parts and any(w in scenario for w in ('missing', 'absent', 'reported missing')):
            if 'side parts' in scenario or 'battery' in scenario:
                missing_parts = [p for p in parts if any(k in p.lower() for k in REFURBISH_PARTS)]
            elif 'main part' in scenario:
                missing_parts = parts[:1]
            elif 'far fewer' in scenario or 'fewer pieces' in scenario:
                missing_parts = parts[:1]

    # Apply rules in order
    n_missing = len(missing_parts)
    has_replaceable_missing = any(k in ' '.join(missing_parts).lower() for k in REFURBISH_PARTS)

    if not has_photo and 'no_return_photo' in scenario:
        disp = 'pending_review'
        rule = 'R01_NO_PHOTO'
    elif not has_photo and has_replaceable_missing:
        disp = 'refurbish'
        rule = 'R09_REPLACEABLE (no photo)'
    elif not has_photo and n_missing > 0:
        disp = 'liquidate'
        rule = 'R10_MISSING_MAIN'
    elif not has_photo:
        disp = 'pending_review'
        rule = 'R01_NO_PHOTO'
    elif id_mismatch:
        disp = 'wrong_product'
        rule = 'R03_ID_MISMATCH'
    elif is_visual_mismatch:
        disp = 'wrong_product'
        rule = 'R03_VISUAL'
    elif category == 'grocery_ingestible':
        disp = 'dispose'
        rule = 'R08_CONSUMABLE'
    elif has_damage:
        disp = 'dispose'
        rule = 'R10_DAMAGE'
    elif category == 'pet':
        disp = 'liquidate'
        rule = 'R07_PET'
    elif has_replaceable_missing:
        disp = 'refurbish'
        rule = 'R09_REPLACEABLE'
    elif n_missing > 0 or is_worn:
        disp = 'liquidate'
        rule = 'R10_LIQUIDATE'
    elif category == 'beauty_topical':
        disp = 'restock'
        rule = 'R06_BEAUTY_SEALED'
    else:
        disp = 'restock'
        rule = 'R13_COMPLETE'

    marker = ' *** REFURBISH ***' if disp == 'refurbish' else ''
    print(f"{unit:<22} {category:<20} {','.join(parts):<35} {'YES' if has_photo else 'NO':<12} "
          f"{scenario[:48]:<50} {disp:<15} [{rule}]{marker}")

print()
print("=" * 80)
print("REFURBISH RULE triggers when:")
print("  R09: missing_parts includes battery, cover, cable, accessory, or adapter")
print()
print("CHECKING which rows have replaceable-part mentions in scenario/parts_list:")
for row in rows:
    unit = row.get('unit_id', '').strip()
    parts_list = row.get('parts_list', '').strip().lower()
    scenario = row.get('scenario', '').strip().lower()
    has_ref_part = any(k in parts_list for k in REFURBISH_PARTS)
    scen_has_ref = any(k in scenario for k in REFURBISH_PARTS)
    if has_ref_part or scen_has_ref:
        print(f"  {unit}: parts_list={parts_list!r}  scenario_has_replaceable={scen_has_ref}")
