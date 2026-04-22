from __future__ import annotations

from pathlib import Path


def test_workbench_guide_matches_browser_chainlit_workflow() -> None:
    guide = (Path(__file__).resolve().parents[1] / "docs" / "WORKBENCH_GUIDE.md").read_text(encoding="utf-8")
    assert "Chainlit" in guide
    assert "./ttt.sh web" in guide
    assert "Qwen" not in guide


def test_readme_uses_wireguard_llama_cpp_default() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert "http://10.0.0.1:8080/v1" in readme
