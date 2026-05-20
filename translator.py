import urllib.request
import urllib.parse
import json
import re
import time
import sys
from typing import Any, Dict, List, Set, Union

# Character map for Turkish to English/ASCII conversion
TURKISH_TO_ASCII_MAP = {
    'ç': 'c', 'Ç': 'C',
    'ğ': 'g', 'Ğ': 'G',
    'ı': 'i', 'İ': 'I',
    'ö': 'o', 'Ö': 'O',
    'ş': 's', 'Ş': 'S',
    'ü': 'u', 'Ü': 'U'
}

def replace_turkish_chars(text: str) -> str:
    """Replaces Turkish-only characters with their English/ASCII counterparts."""
    if not isinstance(text, str):
        return text
    for tr_char, ascii_char in TURKISH_TO_ASCII_MAP.items():
        text = text.replace(tr_char, ascii_char)
    return text

def translate_batch(lines: List[str], source_lang: str = "en", target_lang: str = "tr") -> List[str]:
    """Translates a batch of strings using Google Translate API, preserving placeholders."""
    if not lines:
        return []
    
    # 1. Join lines with newline
    combined_text = "\n".join(lines)
    
    # 2. Find and preserve placeholders (e.g. {hp}, *bleed*)
    # Using regex to find all matches of {placeholder} or *placeholder*
    placeholder_pattern = r"\{[a-zA-Z_0-9\-]+\}|\*[a-zA-Z_0-9\-]+\*"
    placeholders = re.findall(placeholder_pattern, combined_text)
    
    temp_text = combined_text
    for i, placeholder in enumerate(placeholders):
        # Use a highly unique tag to prevent translation
        temp_text = temp_text.replace(placeholder, f"__PH_{i}__")
        
    # 3. Call Google Translate API
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl={source_lang}&tl={target_lang}&q={urllib.parse.quote(temp_text)}"
    
    translated_text = ""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
        translated_parts = []
        for part in res_data[0]:
            if part[0]:
                translated_parts.append(part[0])
        translated_text = "".join(translated_parts)
    except Exception as e:
        print(f"Error translating batch: {e}", file=sys.stderr)
        # Fallback: Translate each line individually
        return [translate_single(line, source_lang, target_lang) for line in lines]

    # 4. Restore placeholders and clean spacing around them
    # Google Translate sometimes inserts spaces like "__ PH_0 __" or "__PH_ 0__"
    translated_text = re.sub(r"__\s*PH\s*_\s*(\d+)\s*__", r"__PH_\1__", translated_text)
    for i, placeholder in enumerate(placeholders):
        translated_text = translated_text.replace(f"__PH_{i}__", placeholder)
        
    # 5. Split back into lines
    translated_lines = translated_text.split("\n")
    
    # If the lines length doesn't match, fallback to translating line by line to keep alignment
    if len(translated_lines) != len(lines):
        print(f"Warning: Batch translation line mismatch ({len(translated_lines)} vs {len(lines)}). Falling back to individual translation.", file=sys.stderr)
        return [translate_single(line, source_lang, target_lang) for line in lines]
        
    return translated_lines

def translate_single(text: str, source_lang: str = "en", target_lang: str = "tr") -> str:
    """Translates a single string, preserving placeholders."""
    if not text.strip():
        return text
        
    placeholder_pattern = r"\{[a-zA-Z_0-9\-]+\}|\*[a-zA-Z_0-9\-]+\*"
    placeholders = re.findall(placeholder_pattern, text)
    
    temp_text = text
    for i, placeholder in enumerate(placeholders):
        temp_text = temp_text.replace(placeholder, f"__PH_{i}__")
        
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl={source_lang}&tl={target_lang}&q={urllib.parse.quote(temp_text)}"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode('utf-8'))
        
        translated_parts = [part[0] for part in res_data[0] if part[0]]
        translated_text = "".join(translated_parts)
    except Exception as e:
        print(f"Error translating single text '{text}': {e}", file=sys.stderr)
        return text
        
    translated_text = re.sub(r"__\s*PH\s*_\s*(\d+)\s*__", r"__PH_\1__", translated_text)
    for i, placeholder in enumerate(placeholders):
        translated_text = translated_text.replace(f"__PH_{i}__", placeholder)
        
    return translated_text

def collect_all_strings(data: Any, strings_set: Set[str]) -> None:
    """Recursively collects all leaf string values from the JSON data."""
    if isinstance(data, dict):
        for val in data.values():
            collect_all_strings(val, strings_set)
    elif isinstance(data, list):
        for item in data:
            collect_all_strings(item, strings_set)
    elif isinstance(data, str):
        if data.strip():
            strings_set.add(data)

def apply_translations(data: Any, translation_map: Dict[str, str]) -> Any:
    """Recursively replaces string values with their translations."""
    if isinstance(data, dict):
        return {key: apply_translations(val, translation_map) for key, val in data.items()}
    elif isinstance(data, list):
        return [apply_translations(item, translation_map) for item in data]
    elif isinstance(data, str):
        if data.strip():
            return translation_map.get(data, data)
        return data
    return data

def translate_json(input_filepath: str, output_filepath: str, batch_size: int = 40) -> None:
    """Reads input JSON, translates all values, and writes output JSON."""
    print(f"Loading {input_filepath}...")
    with open(input_filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # 1. Collect all unique strings
    unique_strings_set = set()
    collect_all_strings(data, unique_strings_set)
    unique_strings = sorted(list(unique_strings_set))
    total_strings = len(unique_strings)
    print(f"Found {total_strings} unique strings to translate.")
    
    # 2. Translate in batches
    translation_map = {}
    for i in range(0, total_strings, batch_size):
        batch = unique_strings[i:i+batch_size]
        print(f"Translating batch {i // batch_size + 1}/{(total_strings + batch_size - 1) // batch_size} (strings {i} to {min(i+batch_size, total_strings)})...")
        
        translated_batch = translate_batch(batch)
        
        # Convert Turkish characters in the translated batch to English/ASCII
        cleaned_batch = [replace_turkish_chars(t) for t in translated_batch]
        
        for orig, trans in zip(batch, cleaned_batch):
            translation_map[orig] = trans
            
        # Polite sleep to avoid hitting API rate limits too aggressively
        time.sleep(0.5)
        
    # 3. Apply translations to the original structure
    print("Applying translations to JSON structure...")
    translated_data = apply_translations(data, translation_map)
    
    # 4. Save to output file
    print(f"Saving translated JSON to {output_filepath}...")
    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(translated_data, f, indent=2, ensure_ascii=True)
    print("Translation complete!")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python translator.py <input_json> <output_json>")
    else:
        translate_json(sys.argv[1], sys.argv[2])
