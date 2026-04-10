import os
import json
import glob
import random
import string
from datetime import datetime
from pathlib import Path
import requests

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ttt_core.llm import LlamaCppClient

# ==== Configuration ====
FLAT_BIBLES_DIR = '001_Flat_Bibles'
INSTRUCTIONS_FILE = 'instructions_bible_crafter_prompt.txt'
CHAT_SESSION_DIR = '002_Chat_Session'
OUTPUT_DIR = '003_Output'

LLAMA_CPP_CLIENT = LlamaCppClient()

def safe_filename(s):
    return s.replace(':', '_').replace('-', '_')

def random_chunk_id(prefix):
    nnn = ''.join(random.choices(string.digits, k=3))
    xxx = ''.join(random.choices(string.ascii_uppercase, k=3))
    yyy = prefix.upper()
    return f"chunk_id_{nnn}{xxx}{yyy}"

def extract_verses(bible_file, book, chapter, v_start, v_end):
    with open(bible_file, 'r', encoding='utf-8') as f:
        verses = json.load(f)
    results = []
    for v in verses:
        if (v['book'].lower() == book.lower()
                and int(v['chapter']) == int(chapter)
                and int(v_start) <= int(v['verse']) <= int(v_end)):
            results.append((int(v['verse']), v['text']))
    results.sort()
    return results

def fetch_llm_models():
    return LLAMA_CPP_CLIENT.list_models()

def ollama_generate(model, prompt):
    try:
        data = {
            "model": model,
            "prompt": prompt,
            "stream": True
        }
        # Stream must be True in both data and requests.post
        resp = requests.post(OLLAMA_GENERATE_API, json=data, stream=True, timeout=None)
        resp.raise_for_status()
        output_text = ""
        for line in resp.iter_lines(decode_unicode=True):
            if not line.strip():
                continue
            # Ollama streams each chunk as a JSON line: {"response": "...", ...}
            try:
                j = json.loads(line)
                token = j.get("response", "")
                print(token, end="", flush=True)  # Print live!
                output_text += token
            except Exception as ex:
                print(f"\n[Streaming Parse Error]: {ex}")
        print()  # Final newline after streaming
        return output_text
    except Exception as e:
        print(f"Error generating output from Ollama: {e}")
        return None

def get_file_prefix(filename):
    # Extracts the 3-letter code (like 'CSB') from filenames like '3_CSB_Bible_flat.json'
    parts = filename.split('_')
    if len(parts) >= 2:
        return parts[1][:3].upper()
    return "UNK"

def main():
    os.makedirs(CHAT_SESSION_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    chunk_addr = input("Enter chunk address (BookName:Chapter:Verse-Range, e.g., Matthew:1:1-17): ").strip()
    try:
        book, chapter, verse_range = chunk_addr.split(':')
        v_start, v_end = verse_range.replace('-', '_').split('_')
    except ValueError:
        print("Invalid format! Example: Matthew:1:1-17")
        return

    flat_bibles = sorted(
        [f for f in glob.glob(os.path.join(FLAT_BIBLES_DIR, '*_Bible_flat.json')) if not os.path.basename(f).startswith('_')],
        key=lambda x: os.path.basename(x)
    )

    if not flat_bibles:
        print(f"No flat bibles found in {FLAT_BIBLES_DIR}!")
        return

    print("\nAvailable Source Translations:")
    for i, f in enumerate(flat_bibles, 1):
        print(f"[{i}] {os.path.basename(f)}")

    selection = input("\nSelect translations to use (e.g., 1,3,5 or 'all'): ").strip().lower()
    
    if selection == 'all' or selection == '':
        selected_bibles = flat_bibles
    else:
        try:
            indices = [int(x.strip()) - 1 for x in selection.split(',')]
            selected_bibles = [flat_bibles[i] for i in indices if 0 <= i < len(flat_bibles)]
        except (ValueError, IndexError):
            print("Invalid selection! Using all translations.")
            selected_bibles = flat_bibles

    chunk_outputs = []
    for bible_file in selected_bibles:
        filename = os.path.basename(bible_file)
        prefix = get_file_prefix(filename)
        chunk_id = random_chunk_id(prefix)
        verses = extract_verses(bible_file, book, chapter, v_start, v_end)
        if not verses:
            continue
        chunk_text = [f"{chunk_id}"]
        for verse_num, verse_text in verses:
            chunk_text.append(f"{verse_num}. {verse_text}")
        chunk_outputs.append('\n'.join(chunk_text))

    if not chunk_outputs:
        print("No verses found for the given chunk address!")
        return

    # --- Read the instructions prompt (place at the top) ---
    try:
        with open(INSTRUCTIONS_FILE, encoding='utf-8') as f:
            instructions_prompt = f.read().strip()
    except FileNotFoundError:
        print(f"Instructions file '{INSTRUCTIONS_FILE}' not found!")
        return

    timestamp = datetime.now().strftime('%d%m%y_%H%M%S')
    session_filename = safe_filename(f"{book}_{chapter}_{v_start}_{v_end}_{timestamp}.txt")
    session_filepath = os.path.join(CHAT_SESSION_DIR, session_filename)

    # --- Write: prompt first, then --- separator, then all chunks (2 newlines between each chunk) ---
    with open(session_filepath, 'w', encoding='utf-8') as f:
        f.write(instructions_prompt)
        f.write('\n---\n')
        f.write('\n\n'.join(chunk_outputs))

    print(f"\nChat session file created: {session_filepath}")

    # --- Model selection ---
    models = fetch_llm_models()
    if not models:
        print("No models found (is llama.cpp server running at 192.168.1.186:8080?)")
        # Fallback to a default name
        models = ["llama.cpp-model"]

    print("\nAvailable models:")
    for i, m in enumerate(models, 1):
        print(f"[{i}] {m}")

    selected = models[0] # Default to first
    if len(models) > 1:
        while True:
            try:
                pick = int(input("\nSelect model by number: ").strip())
                if 1 <= pick <= len(models):
                    selected = models[pick-1]
                    break
                else:
                    print("Invalid selection. Try again.")
            except ValueError:
                print("Please enter a valid number.")

    print(f"\nYou selected: {selected}")

    # --- Feed to llama.cpp, save output as Markdown ---
    try:
        with open(session_filepath, encoding='utf-8') as f:
            prompt_content = f.read()
    except Exception as e:
        print(f"Failed to read chat session file: {e}")
        return

    print("\nSending prompt to llama.cpp... This may take a while.\n")
    
    response_text = ""
    for chunk in LLAMA_CPP_CLIENT.stream_generation(selected, prompt_content, temperature=0.7):
        if chunk.startswith("__STATS_BLOCK__"):
            continue
        print(chunk, end="", flush=True)
        response_text += chunk
    print()

    if not response_text:
        print("Failed to get response from llama.cpp.")
        return

    output_filename = os.path.splitext(os.path.basename(session_filepath))[0] + '.md'
    output_filepath = os.path.join(OUTPUT_DIR, output_filename)
    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(response_text)
        print(f"\nOutput saved to: {output_filepath}")
    except Exception as e:
        print(f"Failed to write output: {e}")

if __name__ == "__main__":
    main()
