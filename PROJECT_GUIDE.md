# TTT Bible Translation Project: Comprehensive Workflow Guide

## 1. Project Overview
The **TTT (Theological Truth Translation) Bible Project** is a high-fidelity Bible translation workflow that combines Local Large Language Models (LLMs) with expert human editorial oversight. The goal is to produce a refined, justified, and consistent Bible translation delivered in a professional EPUB format.

### **Core Objective**
To use multiple source translations and original Greek/Hebrew texts (via LLMs) to generate a new translation, which is then refined by a human editor and compiled into a production-ready EPUB.

---

## 2. Infrastructure & LLM Setup
The project has been migrated from Ollama to **llama.cpp** for improved local performance and control.

*   **Primary Endpoint:** `http://192.168.1.186:8080`
*   **Client Logic:** Located in `01_AI_Translation_Engine/llm_clients.py`. 
*   **Configuration:** The scripts are configured to use the `/completion` endpoint of llama.cpp, allowing for streaming output directly in the terminal.

---

## 3. Directory Structure & Workflow Stages

The project is organized into four sequential stages (00–03). Each stage contains a shell script wrapper (`.sh`) to simplify execution.
### **Stage 00: Data Converters**
...
*   **Original Language Sources:**
    *   **Hebrew (MT):** `00_Data_Converters/_Original_Languages/HEBREW/WLC.json` (Westminster Leningrad Codex).
    *   **Hebrew (Morph):** `00_Data_Converters/_Original_Languages/HEBREW/morphhb_xml/` (With grammatical data).
    *   **Greek (GNT):** `00_Data_Converters/_Original_Languages/GREEK/StatResGNT.json` and `TR.json`.
    *   **Septuagint (LXX):** Available in `00_Data_Converters/bible_databases/formats/json/` as `GreVamvas.json` or `HebModern.json` for comparison.

    ### **Stage 01: AI Translation Engine**
    *   **Purpose:** The "Heavy Lifting" stage. Running LLM loops to generate verses and justifications.
    *   **Updated Feature:** You can now **select specific translations** (e.g., SBLGNT + 2 others) when running the script to keep the context focused on original language analysis.
    *   **Key Tools:** 
        *   `TTT_Bible_crafter.py`: The main script that feeds source Bibles and prompts to the LLM.
        *   `instructions_bible_crafter_prompt.txt`: The "Delta Analysis" prompt focused on literalness and word variants.
    ...
    ## 5. Utilities & Maintenance
    ...
    ### **Cleanup & Archiving**
    Outdated and experimental files have been moved to `_01_DEPRECATED/` and compressed into `_01_DEPRECATED_BACKUP.rar` using high compression (RAR m5) to keep the workspace clean while preserving research history.

    *   `001_Flat_Bibles/`: Storage for the 14+ source translations used as context.
*   **Execution:**
    ```bash
    cd 01_AI_Translation_Engine
    ./translate_verse.sh
    ```
    *Input format:* `Book:Chapter:Verse-Range` (e.g., `Matthew:1:1-17`).
    *Output:* Markdown files in `003_Output/` containing the translation + justifications.

### **Stage 02: Human Editorial Workspace**
*   **Purpose:** The "Human-in-the-loop" phase. The editor reviews the AI's justifications and decides on the final wording.
*   **Key Tools:** 
    *   `bible_translation_tool.py`: Provides theological fidelity and stylistic scoring.
    *   `consistency.py`: Ensures key terms are translated the same way across chapters.
*   **Execution:**
    ```bash
    cd 02_Human_Editorial_Workspace
    ./analyze_translation.sh
    ```

### **Stage 3: EPUB Production**
*   **Purpose:** Converting the final, editor-approved JSON files into a professional ebook.
*   **Key Tools:**
    *   `generate_epub.py`: The assembly engine.
    *   `_HOLY_BIBLE/`: The source directory for finalized JSON chapters.
    *   `Word_Choice_Rules_...yaml`: Formatting and stylistic rules for the builder.
*   **Execution:**
    ```bash
    cd 03_EPUB_Production
    ./make_epub.sh
    ```

---

## 4. Operational Sequence (The "Standard Day")

1.  **Select a Passage:** Choose a chapter to translate (e.g., John 1).
2.  **Run AI Engine:** Use `./translate_verse.sh` in folder `01`.
3.  **Review Justifications:** Read the Markdown file in `01/003_Output`. Look at the "Justification" section to see why the AI chose specific Greek nuances.
4.  **Edit Final JSON:** Move the approved text into the corresponding JSON file in `03_EPUB_Production/_HOLY_BIBLE/`.
5.  **Audit Consistency:** Use the tools in folder `02` to ensure you haven't introduced contradictions.
6.  **Build EPUB:** Run `./make_epub.sh` in folder `03` to see the results in your ebook reader.

---

## 5. Utilities & Maintenance

### **Version Control & Backups**
I have replaced all PowerShell backup scripts with a unified Python script.
*   **Tool:** `version_control.py` (located in the root).
*   **Usage:** `python3 version_control.py`
*   **Function:** Creates a timestamped, versioned copy (e.g., `v005`) of the entire project in the `version_backup/` folder, excluding the backup folder itself to prevent recursion.

### **Adding New Sources**
To add a new translation as a source:
1.  Place the raw file in `00_Data_Converters`.
2.  Run the appropriate converter to get a `.json` file.
3.  Move the resulting `_flat.json` to `01_AI_Translation_Engine/001_Flat_Bibles/`.

---
**Document Version:** 1.0  
**Updated:** Wednesday, April 8, 2026
