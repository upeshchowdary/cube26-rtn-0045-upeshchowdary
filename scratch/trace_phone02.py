"""Trace PHONE-02 scenario parsing step by step."""
scenario_text = 'side parts (battery + battery cover) reported missing. no genuine photo of this exact staged scenario exists, left blank on purpose. unlike watch-02/phone-03, these are side/essential/replaceable parts (not the first-listed main part).'.lower()
parts_list_str = 'handset;battery;battery cover'
expected_p = [p.strip() for p in parts_list_str.split(';') if p.strip()]

REFURBISH_PARTS = ('battery', 'cover', 'cable', 'accessory', 'adapter')

print(f"Scenario: {scenario_text[:80]}...")
print(f"Parts: {expected_p}")
print()

detected_missing = []
for p in expected_p:
    p_lower = p.lower()
    matched = (
        f'{p_lower} itself' in scenario_text
        or f'{p_lower} reported missing' in scenario_text
        or f'{p_lower} reported absent' in scenario_text
        or f'{p_lower} is missing' in scenario_text
        or f'{p_lower} missing' in scenario_text
        or f'{p_lower} absent' in scenario_text
        or f'({p_lower})' in scenario_text
        or f'{p_lower} +' in scenario_text
        or f'+ {p_lower}' in scenario_text
    )
    has_missing_word = any(w in scenario_text for w in ('missing', 'absent', 'not included', 'fewer', 'lost', 'without'))
    print(f"  Part: {p!r:25} individual_match={matched}  global_missing_word={has_missing_word}")
    if matched and has_missing_word:
        detected_missing.append(p)

print(f"\nPer-part detected: {detected_missing}")

if not detected_missing:
    print("\nFalling back to group patterns...")
    if ('side parts' in scenario_text or 'accessories' in scenario_text) and any(w in scenario_text for w in ('missing', 'absent', 'without')):
        if len(expected_p) > 1:
            detected_missing.extend(expected_p[1:])
        print(f"  Side-parts fallback triggered: {detected_missing}")

has_replaceable = any(k in ' '.join(detected_missing).lower() for k in REFURBISH_PARTS)
print(f"\nFinal missing: {detected_missing}")
print(f"Has replaceable parts missing: {has_replaceable}")
print(f"Expected disposition: {'refurbish' if has_replaceable else 'liquidate'}")
print()

# Now check what's actually happening with 'battery cover'
p = 'battery cover'
print(f"Detailed check for 'battery cover':")
print(f"  '(battery cover)' in scenario: {'(battery cover)' in scenario_text}")
print(f"  'battery cover +' in scenario: {'battery cover +' in scenario_text}")
print(f"  '+ battery cover' in scenario: {'+ battery cover' in scenario_text}")
print(f"  'battery cover missing' in scenario: {'battery cover missing' in scenario_text}")
print(f"  'battery cover)' in scenario: {'battery cover)' in scenario_text}")
# The scenario has "(battery + battery cover)"
# So '+ battery cover' should match!
print(f"  FULL scenario battery cover context: {scenario_text[scenario_text.find('battery'):scenario_text.find('battery')+50]}")
