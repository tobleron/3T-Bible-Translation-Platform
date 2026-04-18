from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def live_server_url() -> Iterator[str]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'src'}:{ROOT}{':' + env['PYTHONPATH'] if env.get('PYTHONPATH') else ''}"
    env["TTT_WEBAPP_FAKE_LLM"] = "1"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "ttt_webapp.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=1)
                raise RuntimeError(f"uvicorn exited early\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("uvicorn did not start within 20 seconds")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture()
def page(live_server_url: str) -> Iterator[Page]:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        yield page
        context.close()
        browser.close()


def open_workspace(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/workspace/old/genesis/1/1-5", wait_until="networkidle")
    expect(page.locator("#workspace-shell")).to_be_visible()


def test_chat_panel_swap_keeps_workspace_and_recovers_button(page: Page, live_server_url: str) -> None:
    open_workspace(page, live_server_url)
    page.evaluate("document.querySelector('#workspace-shell').dataset.playwrightMarker = 'kept'")

    def slow_chat_session(route):
        time.sleep(0.25)
        route.continue_()

    page.route("**/chat/session/new", slow_chat_session)
    new_button = page.locator(".chat-new-button")
    new_button.click()
    expect(page.locator("#chat-panel")).to_be_visible()
    expect(page.locator("#workspace-shell")).to_have_attribute("data-playwright-marker", "kept")
    expect(page.locator(".chat-new-button")).to_be_enabled()
    expect(page.locator("#chat-panel iframe")).to_be_visible()


def test_stream_controller_recovers_send_and_stop_controls(page: Page, live_server_url: str) -> None:
    open_workspace(page, live_server_url)
    recovered = page.evaluate(
        """
        () => {
          const host = document.createElement('div');
          host.innerHTML = `
            <form id="chat-stream-form">
              <button class="send-button" data-original-label="Send">Streaming...</button>
            </form>
            <button id="chat-stop-button" class="is-animating" style="display:flex"></button>
          `;
          document.body.appendChild(host);
          const state = window.TTTChatStreamController.state();
          state.controller = new AbortController();
          state.done = false;
          const signal = state.controller.signal;
          document.querySelector('.send-button').disabled = true;
          window.TTTChatStreamController.restoreControls();
          return {
            done: state.done,
            aborted: signal.aborted,
            sendDisabled: document.querySelector('.send-button').disabled,
            sendLabel: document.querySelector('.send-button').textContent,
            stopDisplay: document.querySelector('#chat-stop-button').style.display,
            stopAnimating: document.querySelector('#chat-stop-button').classList.contains('is-animating')
          };
        }
        """
    )
    assert recovered == {
        "done": True,
        "aborted": True,
        "sendDisabled": False,
        "sendLabel": "Send",
        "stopDisplay": "none",
        "stopAnimating": False,
    }


def test_study_source_checkbox_adds_translation_block(page: Page, live_server_url: str) -> None:
    open_workspace(page, live_server_url)
    kjv_toggle = page.locator('[data-study-source-toggle][value="KJV"]')
    kjv_block = page.locator('#study-blocks .translation-block[data-translation-alias="KJV"]')

    expect(kjv_toggle).not_to_be_checked()
    expect(kjv_block).to_have_count(0)

    kjv_toggle.check()

    expect(kjv_toggle).to_be_checked()
    expect(kjv_block).to_have_count(1)
    expect(kjv_block.locator(".translation-verse-row")).not_to_have_count(0)


def test_new_study_translation_respects_active_verse_filter(page: Page, live_server_url: str) -> None:
    open_workspace(page, live_server_url)
    kjv_toggle = page.locator('[data-study-source-toggle][value="KJV"]')
    kjv_block = page.locator('#study-blocks .translation-block[data-translation-alias="KJV"]')

    if kjv_toggle.is_checked():
        kjv_toggle.uncheck()
        expect(kjv_block).to_have_count(0)

    page.locator("#study-verse-filter").fill("1-2")
    page.locator("#study-verse-filter-apply").click()
    kjv_toggle.check()
    expect(kjv_block).to_have_count(1)

    visibility = kjv_block.evaluate(
        """
        (block) => Array.from(block.querySelectorAll('.translation-verse-row[data-verse]')).map((row) => ({
          verse: row.getAttribute('data-verse'),
          visible: row.style.display !== 'none'
        }))
        """
    )
    assert visibility
    assert {row["verse"] for row in visibility if row["visible"]} <= {"1", "2"}
    assert any(row["verse"] == "3" and not row["visible"] for row in visibility)


def test_filtered_prompt_uses_study_checkbox_order(page: Page, live_server_url: str) -> None:
    open_workspace(page, live_server_url)
    filtered_text = page.evaluate(
        """
        () => {
          const sheet = document.querySelector('#study-blocks');
          sheet.querySelectorAll('.translation-block').forEach((block) => block.remove());
          ['NLT', 'NKJV', 'NET'].forEach((alias) => {
            const block = document.createElement('div');
            block.className = 'chunk-block translation-block';
            block.setAttribute('data-translation-alias', alias);
            block.innerHTML = `
              <div class="translation-verse-row" data-verse="1">
                <span class="translation-verse-text">${alias} text</span>
              </div>
            `;
            sheet.appendChild(block);
          });
          return window.currentStudySelectedTranslationsPromptText();
        }
        """
    )

    assert filtered_text.index("NKJV:") < filtered_text.index("NLT:")
    assert filtered_text.index("NLT:") < filtered_text.index("NET:")


def test_copy_translation_uses_fallback_when_clipboard_api_fails(page: Page, live_server_url: str) -> None:
    open_workspace(page, live_server_url)
    result = page.evaluate(
        """
        async () => {
          const button = document.createElement('button');
          button.textContent = 'Copy';
          document.body.appendChild(button);
          let copied = '';
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: { writeText: () => Promise.reject(new Error('blocked')) }
          });
          const originalExecCommand = document.execCommand;
          document.execCommand = (command) => {
            if (command !== 'copy') return false;
            copied = document.activeElement.value;
            return true;
          };
          window.copyTranslationVerse(button, 'fallback copy text');
          await new Promise((resolve) => setTimeout(resolve, 100));
          document.execCommand = originalExecCommand;
          return { copied, label: button.textContent };
        }
        """
    )

    assert result["copied"] == "fallback copy text"
    assert result["label"] == "\u2713"
