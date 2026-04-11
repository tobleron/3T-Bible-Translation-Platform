from __future__ import annotations

import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

import ttt_workbench.app as appmod


class FakeLLM:
    def __init__(self, base_url: str = "http://fake-llm.local") -> None:
        self.base_url = base_url.rstrip("/")

    def list_models(self) -> list[str]:
        return ["Qwen3.5-35B-A3B-Test"]

    def complete(self, prompt: str, *, temperature: float = 0.35, max_tokens: int = 2048, stop: list[str] | None = None) -> str:
        if "Observations:" in prompt and "Wording options:" in prompt:
            return (
                "Observations:\n"
                "- Greek genealogy formula repeats consistently.\n"
                "- Proper names dominate the chunk.\n"
                "Wording options:\n"
                "- fathered\n"
                "- became the father of\n"
                "Cautions:\n"
                "- Keep repetition stable.\n"
                "Direction:\n"
                "Use a consistent literal rendering for the repeated begetting formula."
            )
        return "Plain text response."

    def complete_json(
        self,
        prompt: str,
        *,
        required_keys: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        max_attempts: int = 3,
        timeout_seconds: int = 300,
    ) -> tuple[dict | list | None, str, int]:
        if '"chunks"' in prompt or "Window to segment:" in prompt:
            window_match = re.search(r"Window to segment:\s+(.+?)\s+(\d+):(\d+)-(\d+)", prompt)
            if window_match:
                book = window_match.group(1).strip()
                chapter = int(window_match.group(2))
                start = int(window_match.group(3))
                end = int(window_match.group(4))
            else:
                book, chapter, start, end = "Matthew", 1, 1, 25
            if book.lower() == "matthew" and chapter == 1 and start <= 17 <= end:
                payload = {
                    "book": book,
                    "chapter": chapter,
                    "chunks": [
                        {
                            "start_verse": 1,
                            "end_verse": 17,
                            "type": "genealogy",
                            "title": "Genealogy of Jesus",
                            "reason": "A single genealogy unit with repeated structure.",
                        },
                        {
                            "start_verse": 18,
                            "end_verse": min(25, end),
                            "type": "story",
                            "title": "Birth of Jesus",
                            "reason": "A coherent birth narrative centered on Joseph and the angelic message.",
                        },
                    ],
                }
            else:
                payload = {
                    "book": book,
                    "chapter": chapter,
                    "chunks": [
                        {
                            "start_verse": start,
                            "end_verse": end,
                            "type": "mixed",
                            "title": f"{book} {chapter}",
                            "reason": "Fallback single chunk for smoke testing.",
                        }
                    ],
                }
            return payload, str(payload), 1

        chunk_match = re.search(r"Chunk reference:\s+(.+?)\s+(\d+):(\d+)-(\d+)", prompt)
        if chunk_match and '"title_alternatives"' in prompt:
            start = int(chunk_match.group(3))
            end = int(chunk_match.group(4))
            payload = {
                "reply": "Initial draft generated.",
                "title": "Genealogy of Jesus",
                "verses": [{"verse": verse, "text": f"Draft verse {verse}."} for verse in range(start, end + 1)],
                "title_alternatives": ["Jesus' Genealogy", "Line of Jesus"],
            }
            return payload, str(payload), 1

        if "interactive terminal workbench" in prompt:
            focus_match = re.search(r"Current focus:\s+verses\s+(\d+)-(\d+)", prompt)
            start = int(focus_match.group(1)) if focus_match else 1
            end = int(focus_match.group(2)) if focus_match else start
            payload = {
                "reply": "Draft revised for the current focus.",
                "title": "Genealogy of Jesus",
                "verses": [{"verse": verse, "text": f"Refined verse {verse}."} for verse in range(start, end + 1)],
            }
            return payload, str(payload), 1

        if '"summary"' in prompt and '"verdict"' in prompt:
            payload = {
                "summary": "The draft is coherent and grammatically stable.",
                "issues": ["Consider whether 'fathered' should stay consistent in every verse."],
                "verdict": "ready",
                "title_review": "Title is acceptable.",
            }
            return payload, str(payload), 1

        if '"alternatives"' in prompt and '"reason"' in prompt:
            payload = {
                "title": "Genealogy of Jesus",
                "alternatives": ["Jesus' Genealogy", "Line of Jesus"],
                "reason": "Short, plain, and suitable as a section heading.",
            }
            return payload, str(payload), 1

        if '"source_term"' in prompt and '"decision"' in prompt and '"reason"' in prompt:
            payload = {
                "source_term": "γεννάω",
                "decision": "fathered",
                "reason": "The repeated genealogy formula is rendered consistently with a compact literal choice.",
            }
            return payload, str(payload), 1

        if '"text"' in prompt and "Task type: editorial enhancement" in prompt:
            source_match = re.search(r"Source text:\s*(.*?)\s*Return strict JSON only:", prompt, re.S)
            text = source_match.group(1).strip() if source_match else "Edited text."
            instruction_match = re.search(r"Instruction:\s*(.*?)\s*Context:", prompt, re.S)
            instruction = instruction_match.group(1).strip().lower() if instruction_match else ""
            if "copyeditor" in instruction or "grammar" in instruction:
                result = text.replace(" teh ", " the ").replace(" dont ", " don't ")
            elif "concise" in instruction or "compressor" in instruction:
                result = re.sub(r"\s+", " ", text).strip()
                result = result[: max(len(result) - 10, 1)] if len(result) > 24 else result
            elif "scholarly" in instruction or "academic" in instruction:
                result = f"Scholarly: {text}"
            else:
                result = f"Revised: {text}"
            payload = {"text": result.strip()}
            return payload, str(payload), 1

        return {}, "{}", 1


def install_safe_patches() -> None:
    def fake_write_backup_set(backups_dir: Path, writes: list[tuple[Path, str, str]]) -> Path:
        backup_dir = Path(tempfile.mkdtemp(prefix="ttt-smoke-", dir=str(backups_dir)))
        manifest_lines = [str(path) for path, _, _ in writes]
        (backup_dir / "manifest.json").write_text("[]", encoding="utf-8")
        (backup_dir / "paths.txt").write_text("\n".join(manifest_lines), encoding="utf-8")
        return backup_dir

    def fake_restore_backup_set(backup_dir: Path) -> list[str]:
        paths_file = backup_dir / "paths.txt"
        if not paths_file.exists():
            return []
        return [line for line in paths_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    def fake_run(cmd, cwd=None, capture_output=True, text=True, check=False):
        return SimpleNamespace(returncode=0, stdout="EPUB dry-run ok\n", stderr="")

    appmod.write_backup_set = fake_write_backup_set
    appmod.restore_backup_set = fake_restore_backup_set
    appmod.subprocess.run = fake_run
