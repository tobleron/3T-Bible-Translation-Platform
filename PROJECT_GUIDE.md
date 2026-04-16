# TTT Bible Translation Project: Comprehensive Workflow Guide

## 1. Project Overview
The **TTT (Theological Truth Translation) Bible Project** is a high-fidelity Bible translation workflow that combines Local Large Language Models (LLMs) with expert human editorial oversight. The goal is to produce a refined, justified, and consistent Bible translation delivered in a professional EPUB format.

### **Core Objective**
To use multiple source translations and original Greek/Hebrew texts (via LLMs) to generate a new translation, which is then refined by a human editor and compiled into a production-ready EPUB.

---

## 2. Infrastructure & LLM Setup
The project uses **llama.cpp** (and optionally OpenAI) for translation and analysis.

*   **Primary Endpoint:** `http://10.0.0.1:8080/v1` over WireGuard (configured in `config.yaml`, `.env`, or `TTT_LLAMA_CPP_BASE_URL`).
*   **Authentication:** No API key is required for the direct WireGuard llama.cpp endpoint.
*   **Client Logic:** Unified clients in `src/ttt_core/llm/`.
    *   `LlamaCppClient`: Handles local llama.cpp server communication.
    *   `OpenAIClient`: Handles OpenAI API communication.

---

## 3. Directory Structure & Modern Workflow

The project is organized into modular packages under the `src/` directory.

### **Core Modules (`src/ttt_core/`)**
*   **`ttt_core.config`**: Unified configuration loader (merges `config.yaml`, environment variables, and defaults).
*   **`ttt_core.data.repositories`**: Centralized data access for:
    *   `BibleRepository`: Main translation storage (`data/final/_HOLY_BIBLE/`).
    *   `SourceRepository`: Reference translations (`data/processed/`).
    *   `JustificationRepository`: LLM-generated justifications.
    *   `LexicalRepository`: Greek/Hebrew lexical data via SQLite.
*   **`ttt_core.llm`**: Unified LLM clients.
*   **`ttt_core.models`**: Shared data structures (dataclasses).

### **AI Translation Engine (`src/ttt_engine/`)**
*   `TTT_Bible_crafter.py`: The main CLI tool for generating translations. It feeds source Bibles and prompts to the LLM.
*   `bible_analysis.py`: Tool for side-by-side comparison of different translations for a given passage.

### **Human Editorial Workspace (`src/ttt_workbench/` & `src/ttt_webapp/`)**
*   **Workbench (TUI):** A Textual-based terminal interface for reviewing and editing translations. Run via `python3 -m ttt_workbench`.
*   **Web App (GUI):** A FastAPI + HTMX web interface providing a modern editing environment. Run via `python3 src/ttt_workbench/webapp.py` (or similar entry point).

### **EPUB Production (`src/ttt_epub/`)**
*   Tools for converting finalized JSON chapters into professional EPUB files.
*   `generate_epub.py`: The assembly engine.

---

## 4. Operational Sequence (The "Standard Day")

1.  **Select a Passage:** Choose a chapter to translate.
2.  **Run AI Engine:** Use `python3 src/ttt_engine/TTT_Bible_crafter.py`.
    *   Enter chunk address (e.g., `John:1:1-18`).
    *   Select source translations for context.
    *   Choose LLM model.
3.  **Review & Edit:** Use the **Workbench** or **Web App** to review the AI's output, justifications, and lexical data.
4.  **Finalize:** Once the translation is approved, it is saved to the `BibleRepository`.
5.  **Build EPUB:** Run the EPUB generation scripts in `src/ttt_epub/` to produce the final ebook.

---

## 5. Utilities & Maintenance

### **Version Control & Backups**
*   **Tool:** `version_control.py` (located in the root).
*   **Function:** Creates timestamped, versioned copies of the entire project in the `version_backup/` folder.
*   **Internal Backups:** `ttt_core.utils.backup` provides atomic writes and per-file backup sets in `.ttt_workbench/backups/`.

### **Data Converters**
*   Located in `src/ttt_converters/`.
*   Used to ingest new Bible formats (SQLite, XML, USFM, etc.) and convert them to the internal "flat JSON" format used by the `SourceRepository`.

---
**Document Version:** 1.1  
**Updated:** Tuesday, April 14, 2026
