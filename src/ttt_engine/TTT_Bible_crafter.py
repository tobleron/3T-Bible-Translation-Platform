import os
import json
import glob
import random
import string
from datetime import datetime
from pathlib import Path
import requests

from ttt_core.llm import LlamaCppClient
from ttt_core.config import load_config
from ttt_core.data.repositories import ProjectPaths, SourceRepository

# ==== Configuration ====
CFG = load_config()
PATHS = ProjectPaths()
SOURCE_REPO = SourceRepository(PATHS)

INSTRUCTIONS_FILE = PATHS.legacy_prompt_path
CHAT_SESSION_DIR = PATHS.sessions_dir
OUTPUT_DIR = PATHS.reports_dir

LLAMA_CPP_CLIENT = LlamaCppClient()

def safe_filename(s):
    return s.replace(':', '_').replace('-', '_')

def random_chunk_id(prefix):
    nnn = ''.join(random.choices(string.digits, k=3))
    xxx = ''.join(random.choices(string.ascii_uppercase, k=3))
    yyy = prefix.upper()
    return f"chunk_id_{nnn}{xxx}{yyy}"

def fetch_llm_models():
    return LLAMA_CPP_CLIENT.list_models()

def main():
    os.makedirs(CHAT_SESSION_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    chunk_addr = input("Enter chunk address (BookName:Chapter:Verse-Range, e.g., Matthew:1:1-17): ").strip()
    try:
        book, chapter_str, verse_range_str = chunk_addr.split(':')
        chapter = int(chapter_str)
        v_start, v_end = map(int, verse_range_str.replace('-', '_').split('_'))
    except ValueError:
        print("Invalid format! Example: Matthew:1:1-17")
        return

    available_sources = SOURCE_REPO.list_sources()
    if not available_sources:
        print("No source translations found!")
        return

    print("\nAvailable Source Translations:")
    for i, alias in enumerate(available_sources, 1):
        print(f"[{i}] {alias}")

    selection = input("\nSelect translations to use (e.g., 1,3,5 or 'all'): ").strip().lower()
    
    if selection == 'all' or selection == '':
        selected_aliases = available_sources
    else:
        try:
            indices = [int(x.strip()) - 1 for x in selection.split(',')]
            selected_aliases = [available_sources[i] for i in indices if 0 <= i < len(available_sources)]
        except (ValueError, IndexError):
            print("Invalid selection! Using all translations.")
            selected_aliases = available_sources

    chunk_outputs = []
    for alias in selected_aliases:
        chunk_id = random_chunk_id(alias[:3])
        verses = SOURCE_REPO.verse_range(alias, book, chapter, v_start, v_end)
        if not verses:
            continue
        chunk_text = [f"{chunk_id}"]
        for verse_num in sorted(verses):
            chunk_text.append(f"{verse_num}. {verses[verse_num]}")
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
