#!/usr/bin/env python3
"""
Bible Translation Analysis Tool (Revised for Robustness and Conversational Workflow)

This tool processes Bible verses through a 4-prompt analysis chain. It features
a robust, session-based workflow with resume capabilities and saves temporary,
approved JSON files for each analysis step.
"""

import os
import json
import re
import yaml
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.progress import Progress
from rich.text import Text

# Re-exported from ttt_core for backward compatibility
from ttt_core.llm import LlamaCppClient, OpenAIClient


class BibleTranslationTool:
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the Bible Translation Tool."""
        self.console = Console()
        self.config = self._load_config(config_path)
        self.llm_client = None
        self.active_model = None
        self.temperature = 0.7
        self.base_output_dir = Path("output")
        self.flat_bibles_dir = Path("flat_bibles")
        self.session_dir = None
        self.temp_dir = None
        
        self.base_output_dir.mkdir(exist_ok=True)
        self.flat_bibles_dir.mkdir(exist_ok=True)
        
        self.prompts = self._load_prompts()

    def _load_config(self, config_path: str) -> dict:
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            self.console.print("[red]Error: config.yaml not found![/red]")
            raise
            
    def _load_prompts(self) -> Dict[str, str]:
        prompt_files = {
            "translation_analysis": "01_translation_analysis.txt",
            "stylistic_score": "02_stylistic_score.txt", 
            "theological_fidelity": "03_theological_fidelity.txt",
            "passage_synthesis": "04_Passage_LevelSynthesis&Analysis.txt"
        }
        prompts = {}
        for key, filename in prompt_files.items():
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    prompts[key] = f.read().strip()
            except FileNotFoundError:
                prompts[key] = ""
        return prompts
        
    def run(self):
        """Main entry point for the tool's workflow."""
        self._welcome()
        if not self._setup_llm(): return
            
        while True:
            try:
                passage_ref = self._get_passage_input()
                if not passage_ref: break
                
                self._setup_session_directories(passage_ref)
                    
                original_file, translation_file = self._select_bible_files()
                if not original_file or not translation_file: continue
                    
                verses_data = self._extract_passage_verses(passage_ref, original_file, translation_file)
                if not verses_data: continue
                
                self._run_supervised_verse_analysis(verses_data)
                
                aggregated_data = self._aggregate_temp_files(verses_data)

                final_result = self._process_passage_analysis(aggregated_data, passage_ref)
                
                output_file = self._save_final_json(final_result, passage_ref)
                
                self.console.print(f"\n[green]✅ Analysis complete! Final output saved to: {output_file}[/green]")

                if self.config.get('cleanup_temp_files', True):
                    shutil.rmtree(self.session_dir)
                    self.console.print("[dim]Temporary session directory has been cleaned up.[/dim]")

                if not Confirm.ask("\nAnalyze another passage?", default=True): break
                    
            except KeyboardInterrupt:
                self.console.print("\n[yellow]\nOperation cancelled by user.[/yellow]")
                break
            except Exception as e:
                self.console.print(f"\n[bold red]An unexpected error occurred: {e}[/bold red]")
                self.console.print_exception(show_locals=True) # For debugging
                continue
                
        self._goodbye()

    def _setup_session_directories(self, passage_ref: str):
        """Creates the session and temporary directories for the run."""
        session_name = f"session_{self._get_filename(passage_ref, with_extension=False)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.session_dir = self.base_output_dir / session_name
        self.temp_dir = self.session_dir / "tmp"
        self.session_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
        self.console.print(f"[dim]Session directory created at: {self.session_dir}[/dim]")

    def _get_temp_json_path(self, verse_ref: str, prompt_key: str) -> Path:
        """Generates a predictable path for a temporary JSON file."""
        safe_verse_ref = verse_ref.replace(":", "-").replace(" ", "_")
        filename = f"{safe_verse_ref}_{prompt_key}.json"
        return self.temp_dir / filename
        
    def _welcome(self):
        welcome_text = Text.from_markup("""
[bold bright_blue]Bible Translation Analysis Tool (Robust Session Mode)[/bold bright_blue]

[bold]Workflow Updates:[/bold]
1. [bold green]Robust Sessions[/bold green]: Each run saves temporary JSON files for every approved step.
2. [bold green]Resume Capability[/bold green]: The script automatically skips previously completed and approved steps.
3. [bold green]Live Chat Review[/bold green]: Refine AI output with live feedback until you `/approve`.
        """)
        self.console.print(Panel(welcome_text, expand=False, border_style="blue"))
        
    def _setup_llm(self) -> bool:
        self.console.print("\n[bold]Select LLM Service:[/bold] ([1] llama.cpp, [2] OpenAI)")
        try:
            choice = IntPrompt.ask("Choice", choices=["1", "2"], default=1)
            service_map = {1: ("llama.cpp", LlamaCppClient), 2: ("OpenAI", OpenAIClient)}
            service_name, client_class = service_map[choice]
            if service_name == "llama.cpp":
                llm_cfg = self.config.get("llama_cpp", {})
                base_url = llm_cfg.get("base_url")
                api_key = llm_cfg.get("api_key")
                self.llm_client = client_class(base_url=base_url, api_key=api_key)
            else:
                self.llm_client = client_class(self.config)
            
            models = self.llm_client.list_models()
            if isinstance(models, str) or not models:
                self.console.print(f"[red]Could not find models for {service_name}[/red]")
                return False
            
            self.console.print(f"\n[bold]Select Model for {service_name}:[/bold]")
            for i, model in enumerate(models): self.console.print(f"  [{i+1}] {model}")
            model_choice = IntPrompt.ask("Model", choices=[str(i+1) for i in range(len(models))])
            self.active_model = models[model_choice-1]
            self.console.print(f"[green]✅ Using {service_name} with model: {self.active_model}[/green]")
            return True
        except (KeyboardInterrupt, EOFError): return False
        except Exception as e:
            self.console.print(f"[red]Error during setup: {e}[/red]")
            return False

    def _get_passage_input(self) -> Optional[str]:
        self.console.print("\n[bold]Enter Passage Reference[/bold] (e.g., 'John 1:1-5')")
        try:
            return Prompt.ask("Passage").strip() or None
        except (KeyboardInterrupt, EOFError): return None
            
    def _select_bible_files(self) -> Tuple[Optional[str], Optional[str]]:
        bible_files = sorted(list(self.flat_bibles_dir.glob("*.json")))
        if not bible_files:
            self.console.print(f"[red]No JSON files found in '{self.flat_bibles_dir}'.[/red]")
            return None, None
            
        self.console.print(f"\n[bold]Available Bible Files:[/bold]")
        for i, file in enumerate(bible_files): self.console.print(f"  [{i+1}] {file.name}")
            
        try:
            orig_choice = IntPrompt.ask("\n[bold]Select Original Text File[/bold]", choices=[str(i+1) for i in range(len(bible_files))])
            trans_choice = IntPrompt.ask("[bold]Select Translation File[/bold]", choices=[str(i+1) for i in range(len(bible_files))])
            original_file, translation_file = bible_files[orig_choice-1], bible_files[trans_choice-1]
            self.console.print(f"[green]✅ Original: {original_file.name}, Translation: {translation_file.name}[/green]")
            return str(original_file), str(translation_file)
        except (KeyboardInterrupt, EOFError): return None, None
            
    def _extract_passage_verses(self, passage_ref: str, original_file: str, translation_file: str) -> Optional[List[Dict]]:
        try:
            with open(original_file, 'r', encoding='utf-8') as f: original_data = json.load(f)
            with open(translation_file, 'r', encoding='utf-8') as f: translation_data = json.load(f)
                
            match = re.match(r'^([A-Za-z0-9\s]+)\s+(\d+):(\d+)(?:-(\d+))?$', passage_ref)
            if not match:
                self.console.print(f"[red]Invalid passage format: '{passage_ref}'[/red]"); return None
                
            book_name, chapter, start_verse, end_verse = match.groups()
            chapter, start_verse = int(chapter), int(start_verse)
            end_verse = int(end_verse) if end_verse else start_verse
            
            verses_data = []
            for verse_num in range(start_verse, end_verse + 1):
                ref_key = f"{book_name.strip()} {chapter}:{verse_num}"
                original_text = self._find_verse_in_data(original_data, book_name.strip(), chapter, verse_num)
                translation_text = self._find_verse_in_data(translation_data, book_name.strip(), chapter, verse_num)
                
                if original_text and translation_text:
                    verses_data.append({"reference": ref_key, "original": original_text, "translation": translation_text})
                else:
                    self.console.print(f"[yellow]Warning: Could not find '{ref_key}'[/yellow]")
                    
            if not verses_data: self.console.print("[red]No verses found.[/red]"); return None
            self.console.print(f"[green]✅ Extracted {len(verses_data)} verses for '{passage_ref}'[/green]")
            return verses_data
        except Exception as e:
            self.console.print(f"[red]Error extracting verses: {e}[/red]"); return None
            
    def _find_verse_in_data(self, data: Dict, book: str, chapter: int, verse: int) -> Optional[str]:
        try:
            if isinstance(data, dict) and book in data and str(chapter) in data.get(book, {}) and str(verse) in data.get(book, {}).get(str(chapter), {}):
                return data[book][str(chapter)][str(verse)]
        except (KeyError, TypeError): pass

        if isinstance(data, dict):
            ref_key = f"{book} {chapter}:{verse}"
            if ref_key in data: return data[ref_key]

        if isinstance(data, list):
            for entry in data:
                if (isinstance(entry, dict) and
                        str(entry.get("book", "")).strip() == book and
                        str(entry.get("chapter")) == str(chapter) and
                        str(entry.get("verse")) == str(verse) and
                        "text" in entry):
                    return entry.get("text")
        return None

    def _clean_markdown(self, text: str) -> str:
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'`(.*?)`', r'\1', text)
        return text.strip()

    def _conduct_chat_review(self, verse_data: Dict, prompt_key: str, initial_ai_response: str, progress_context: str = "", system_prompt_override: Optional[str] = None) -> str:
        """Conducts an interactive chat session to refine and approve an AI analysis."""
        title = prompt_key.replace('_', ' ').title()
        self.console.rule(f"[bold yellow]Chat Review: {title} {progress_context}", style="yellow")
        
        self.console.print(Panel(f"[bold]Original:[/] {verse_data['original']}\n[bold]Translation:[/] {verse_data['translation']}", title=f"Context for {verse_data['reference']}", border_style="blue", expand=False))

        chat_instruction = "\n\n**IMPORTANT**: You are in a review session. Refine your analysis based on my feedback. Incorporate my instructions into your next response until I type '/approve'."
        
        if system_prompt_override:
            system_prompt = system_prompt_override
        else:
            system_prompt = self.prompts.get(prompt_key, title)
    
        messages = [{"role": "system", "content": system_prompt}, {"role": "assistant", "content": initial_ai_response}]
        
        while True:
            ai_response = messages[-1]['content']
            self.console.print(Panel(self._clean_markdown(ai_response), title=f"AI Analysis (v{len(messages)//2})", border_style="green", expand=False))
            
            user_feedback = Prompt.ask("\n[bold]Your feedback (or /approve, /reset, /quit)[/bold]")
            command = user_feedback.lower().strip()

            if command == "/approve":
                self.console.print("[green]✅ Analysis approved![/green]")
                return ai_response
            elif command == "/quit":
                raise KeyboardInterrupt("User quit operation.")
            elif command == "/reset":
                self.console.print("[yellow]Resetting chat for this analysis...[/yellow]")
                messages = messages[:2] 
                continue

            messages.append({"role": "user", "content": user_feedback + chat_instruction})
            
            with self.console.status("[yellow]Thinking...[/yellow]"):
                refined_response = self.llm_client.generate_response(self.active_model, messages, self.temperature)
            
            messages.append({"role": "assistant", "content": refined_response})

    def _conduct_theological_synthesis_chat(self, verse_data: Dict, progress_context: str) -> str:
        """Handles the special two-stage theological analysis within a chat format."""
        self.console.rule("[bold yellow]Theological Fidelity Analysis", style="yellow")
        
        self.console.print("[cyan]Generating AI Consensus Report (Stage 1)...[/cyan]")
        stage1_prompt = "Please act as a research assistant. Analyze the provided verse and generate ONLY the '--- AI Analysis: Consensus Report ---' section based on your instructions. Do NOT generate the 'Human Expert Analysis' or 'Final Holistic Analysis' sections."
        full_initial_prompt = f"{self.prompts['theological_fidelity']}\n\n{stage1_prompt}\n\n---\n**Verse Reference:** {verse_data['reference']}\n**Original Text:** {verse_data['original']}\n**Translation:** {verse_data['translation']}"
        
        with self.console.status("[yellow]Thinking...[/yellow]"):
            ai_consensus_report = self.llm_client.generate_response(self.active_model, full_initial_prompt, self.temperature)

        self.console.print(Panel(self._clean_markdown(ai_consensus_report), title="AI Consensus Report", border_style="cyan"))

        self.console.print("\n[bold]Now, provide your expert exegesis. The AI will then synthesize it with the report above.[/bold]")
        human_exegesis = Prompt.ask("[bold]Your exegesis (or /quit)[/bold]")
        if human_exegesis.lower().strip() == '/quit':
            raise KeyboardInterrupt("User quit operation.")

        self.console.print("\n[cyan]Synthesizing your input with the AI report (Stage 2)...[/cyan]")
        stage2_prompt_template = self.prompts['theological_fidelity']
        final_prompt = stage2_prompt_template.replace(
            '**--- AI Analysis: Consensus Report ---**', f'**--- AI Analysis: Consensus Report ---**\n\n{ai_consensus_report}'
        ).replace(
            '`[This section is reserved for the human expert. After reviewing the AI\'s consensus report, the expert will provide their own critical exegesis here, evaluating minority views, source text nuances, and making a final judgment on the most faithful rendering.]`', human_exegesis
        )

        with self.console.status("[yellow]Thinking...[/yellow]"):
            initial_synthesis = self.llm_client.generate_response(self.active_model, final_prompt, self.temperature)
        
        system_prompt_for_refinement = self.prompts['theological_fidelity']
        final_approved_synthesis = self._conduct_chat_review(
            verse_data, "Theological Synthesis", initial_synthesis, progress_context, system_prompt_override=system_prompt_for_refinement
        )
        return final_approved_synthesis

    def _run_supervised_verse_analysis(self, verses_data: List[Dict]):
        """Main loop to run analysis and review for each verse, with resume capability."""
        prompts_to_run = ["translation_analysis", "stylistic_score"]
        all_prompts = prompts_to_run + ["theological_fidelity"]
        total_steps = len(verses_data) * len(all_prompts)
        
        with Progress(console=self.console) as progress:
            task = progress.add_task("[cyan]Analyzing passage...", total=total_steps)
            
            for i, verse_data in enumerate(verses_data):
                # --- Steps 1 & 2: Standard Prompts ---
                for j, prompt_key in enumerate(prompts_to_run):
                    progress_context = f"[Verse {i+1} of {len(verses_data)} | Step {j+1} of {len(all_prompts)}]"
                    progress.update(task, description=f"Processing {verse_data['reference']} - {prompt_key.replace('_',' ').title()}")

                    temp_json_path = self._get_temp_json_path(verse_data['reference'], prompt_key)
                    if temp_json_path.exists():
                        self.console.print(f"[green]✅ Skipping '{prompt_key}' for '{verse_data['reference']}'. Already approved.[/green]")
                    else:
                        initial_prompt = f"{self.prompts[prompt_key]}\n\n---\n**Verse Reference:** {verse_data['reference']}\n**Original Text:** {verse_data['original']}\n**Translation:** {verse_data['translation']}"
                        initial_response = self.llm_client.generate_response(self.active_model, initial_prompt, self.temperature)
                        
                        progress.stop()
                        approved_response = self._conduct_chat_review(verse_data, prompt_key, initial_response, progress_context)
                        progress.start()
                        
                        temp_data = {"reference": verse_data['reference'], "prompt_type": prompt_key, "response": approved_response}
                        with open(temp_json_path, 'w', encoding='utf-8') as f:
                            json.dump(temp_data, f, indent=2)
                    progress.advance(task)

                # --- Step 3: Special Theological Fidelity Prompt ---
                prompt_key = "theological_fidelity"
                progress_context = f"[Verse {i+1} of {len(verses_data)} | Step 3 of 3]"
                progress.update(task, description=f"Processing {verse_data['reference']} - Theological Fidelity")
                temp_json_path = self._get_temp_json_path(verse_data['reference'], prompt_key)

                if temp_json_path.exists():
                    self.console.print(f"[green]✅ Skipping '{prompt_key}' for '{verse_data['reference']}'. Already approved.[/green]")
                else:
                    progress.stop()
                    approved_response = self._conduct_theological_synthesis_chat(verse_data, progress_context)
                    progress.start()
                    
                    temp_data = {"reference": verse_data['reference'], "prompt_type": prompt_key, "response": approved_response}
                    with open(temp_json_path, 'w', encoding='utf-8') as f:
                        json.dump(temp_data, f, indent=2)
                progress.advance(task)

    def _aggregate_temp_files(self, verses_data: List[Dict]) -> List[Dict]:
        """Reads all temporary JSON files and assembles them into a final data structure."""
        self.console.print("\n[cyan]Aggregating all approved analyses...[/cyan]")
        aggregated_results = []
        all_prompts = ["translation_analysis", "stylistic_score", "theological_fidelity"]
        
        for verse_data in verses_data:
            verse_entry = {
                "reference": verse_data["reference"],
                "original": verse_data["original"],
                "translation": verse_data["translation"],
                "analyses": {}
            }
            for prompt_key in all_prompts:
                temp_json_path = self._get_temp_json_path(verse_data['reference'], prompt_key)
                if temp_json_path.exists():
                    with open(temp_json_path, 'r', encoding='utf-8') as f:
                        verse_entry["analyses"][prompt_key] = json.load(f)
                else:
                    verse_entry["analyses"][prompt_key] = {"error": f"Temporary file for {prompt_key} not found."}
            aggregated_results.append(verse_entry)
        return aggregated_results

    def _process_passage_analysis(self, verse_results: List[Dict], passage_ref: str) -> Dict:
        """Runs the final passage-level synthesis."""
        prompt_template = self.prompts.get("passage_synthesis", "")
        if not prompt_template: return {"error": "Synthesis prompt not found"}
        
        prompt_input_data = []
        for verse in verse_results:
            clean_verse = {
                "reference": verse["reference"],
                "analyses": {
                    "translation_analysis": verse["analyses"].get("translation_analysis", {}).get("response", "N/A"),
                    "stylistic_score": verse["analyses"].get("stylistic_score", {}).get("response", "N/A"),
                    "theological_fidelity": verse["analyses"].get("theological_fidelity", {}).get("response", "N/A")
                }
            }
            prompt_input_data.append(clean_verse)

        full_prompt = f"{prompt_template}\n\n---\n**Passage Reference:** {passage_ref}\n\n**Individual Verse Analyses:**\n{json.dumps(prompt_input_data, indent=2)}"
        
        self.console.print("\n[cyan]Running final passage-level synthesis...[/cyan]")
        try:
            with self.console.status("[yellow]Generating final synthesis...[/yellow]"):
                response_text = self.llm_client.generate_response(self.active_model, full_prompt, self.temperature)
            
            # --- NEW ROBUST JSON PARSING LOGIC ---
            # Find the start of the JSON object
            json_start = response_text.find('{')
            # Find the end of the JSON object
            json_end = response_text.rfind('}')
            
            if json_start != -1 and json_end != -1:
                json_string = response_text[json_start:json_end+1]
                passage_analysis_content = json.loads(json_string)
            else:
                # If no JSON object is found, raise an error to be caught below
                raise json.JSONDecodeError("No JSON object found in the response.", response_text, 0)
            
            return {"passage_reference": passage_ref, "verse_results": verse_results, **passage_analysis_content, "metadata": {"model": self.active_model, "temperature": self.temperature, "total_verses": len(verse_results), "analysis_timestamp": datetime.now().isoformat()}}

        except json.JSONDecodeError:
            self.console.print("[red]LLM did not return valid JSON for the final analysis. Saving raw response.[/red]")
            return {"passage_reference": passage_ref, "verse_results": verse_results, "error": "Failed to parse final analysis as JSON", "raw_response": response_text}
        except Exception as e:
            return {"error": str(e), "verse_results": verse_results}
        
            
    def _get_filename(self, passage_ref: str, with_extension: bool = True) -> str:
        match = re.match(r'^([A-Za-z0-9\s]+)\s+(\d+):(\d+)(?:-(\d+))?$', passage_ref)
        if match:
            book, chap, v_start, v_end = match.groups()
            book, v_end = book.strip().replace(" ", ""), v_end or v_start
            base = f"{book}_{int(chap):03d}_{int(v_start):03d}_{int(v_end):03d}"
            return f"{base}.json" if with_extension else base
        safe_ref = re.sub(r'[^\w\-]', '_', passage_ref)
        return f"analysis_{safe_ref}.json" if with_extension else f"analysis_{safe_ref}"

    def _save_final_json(self, final_result: Dict, passage_ref: str) -> str:
        """Saves the final aggregated JSON to the main output directory."""
        output_filename = self._get_filename(passage_ref)
        output_path = self.base_output_dir / output_filename
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(final_result, f, indent=2, ensure_ascii=False)
            return str(output_path)
        except Exception as e:
            self.console.print(f"[red]Error saving final file: {e}[/red]"); return ""
            
    def _goodbye(self):
        self.console.print("\n[bold blue]Thank you for using the Bible Translation Analysis Tool![/bold blue]")

def main():
    try:
        tool = BibleTranslationTool()
        tool.run()
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
    except Exception as e:
        console = Console()
        console.print(f"\n[bold red]A fatal error occurred: {e}[/bold red]")
        console.print_exception(show_locals=True)

if __name__ == "__main__":
    main()