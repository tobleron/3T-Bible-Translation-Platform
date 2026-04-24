# T038 Troubleshoot Chainlit Hamburger Menu Alignment And Toggle

## Status

Open.

## Objective

Find the root cause of the Chainlit iframe hamburger menu regression where the custom hamburger appears in the wrong place and does not open the sidebar. The intended behavior is for the hamburger to sit on the same visual row and in the same control group as the crescent theme control, then reliably toggle the Chainlit sidebar.

## Observed Failure

Inside the embedded Chainlit chat UI, the custom hamburger button is visually offset from the crescent theme control. It appears lower and further left than intended. Clicking the hamburger does not open the sidebar.

This is not the outer workbench `Chat` menu in `src/ttt_workbench/templates/partials/chat_panel.html`. The failure shown in the screenshot is inside the Chainlit iframe controlled by:

- `public/workbench-chainlit.js`
- `public/workbench-chainlit.css`
- `.chainlit/config.toml`

## Reproduction Steps

1. Launch the browser workbench with `./ttt.sh web`.
2. Open `http://127.0.0.1:8765`.
3. Open any chunk that shows the browser chat panel.
4. Wait for the Chainlit iframe to load.
5. Compare the hamburger button position to the crescent theme control.
6. Click the hamburger button.
7. Observe whether the sidebar opens and whether the button stays aligned with the theme control after the UI settles.

Expected:

- The hamburger sits on the same horizontal level as the crescent theme control.
- The hamburger is inserted into the same visible header control group as the crescent theme control.
- Clicking the hamburger opens or closes the Chainlit sidebar.

Actual:

- The hamburger is misaligned.
- The hamburger click does not open the sidebar.

## Suspected Files

- `public/workbench-chainlit.js`
  - `addHamburgerMenu()`
  - header detection
  - theme/settings control detection
  - sidebar toggle logic
  - fallback click logic
- `public/workbench-chainlit.css`
  - generic `header` and `nav` overrides
  - `.ttt-hamburger-btn`
- `.chainlit/config.toml`
  - custom asset loading
  - sidebar defaults
  - Chainlit version metadata
- `src/ttt_workbench/templates/partials/chat_panel.html`
  - outer workbench chat menu control that can be confused with the broken iframe hamburger during debugging
- `tests/test_chainlit_app.py`
  - currently validates custom Chainlit assets but not hamburger behavior
- `tests/test_playwright_responsiveness.py`
  - likely place for browser-level regression coverage

## Current Code Signals Worth Investigating First

- `public/workbench-chainlit.js` currently guesses the header with very broad selectors:
  - `.cl-header`
  - `[data-testid="cl-header"]`
  - `nav`
  - `header`
  - `[role="banner"]`
- `public/workbench-chainlit.js` inserts the button relative to `themeControl || settingsControl || header.firstChild`, which can miss the actual crescent control or target the wrong container.
- `public/workbench-chainlit.js` tries to toggle the sidebar by manually flipping `open` and `closed` classes, which may not match Chainlit 2.11.0 runtime behavior.
- `public/workbench-chainlit.js` falls back to `document.querySelector('button[aria-label*="sidebar"], button[aria-label*="menu"]')`, which may accidentally match `#ttt-hamburger-menu` itself.
- `public/workbench-chainlit.css` applies a broad layout override to `.cl-header`, `[data-testid="cl-header"]`, `nav`, and `header`, which may be moving the button away from the intended row.
- There is currently no automated test that proves the custom hamburger is positioned correctly or that its click path toggles the sidebar.

## Troubleshooting Checklist

### Scope And Ownership

- [ ] Verify in DevTools that the visible broken hamburger is inside the Chainlit iframe document, not the outer workbench `#chat-panel`.
- [ ] Verify which DOM node owns the visible crescent theme control.
- [ ] Verify whether Chainlit renders multiple candidate headers and whether the injection code is targeting a hidden or wrapper header instead of the visible toolbar row.
- [ ] Verify whether the problem is only in the iframe layer or partly caused by outer workbench layout around the iframe container.

### Placement And Alignment

- [ ] Verify whether `addHamburgerMenu()` selects the wrong header because `nav`, `header`, or `[role="banner"]` is too broad.
- [ ] Verify whether the actual crescent button is inside a nested toolbar group, making insertion at the header root inherently misaligned.
- [ ] Verify whether the `themeControl` selector misses the real crescent control because its live attributes differ from the guessed selector.
- [ ] Verify whether the `settingsControl` selector is matching an unrelated settings control instead of the crescent control.
- [ ] Verify whether the `header.firstChild` fallback resolves to a text node, placeholder node, invisible spacer, or wrapper rather than the first visible control.
- [ ] Verify whether the button is injected into the correct header but the wrong flex row or wrong child group.
- [ ] Verify whether `.ttt-hamburger-btn { order: -1; }` forces the button to the far-left instead of the same control cluster as the crescent button.
- [ ] Verify whether `.ttt-hamburger-btn` margins or padding create the apparent vertical and horizontal drift seen in the screenshot.
- [ ] Verify whether the broad CSS rule `.cl-header, [data-testid="cl-header"], nav, header { justify-content: space-between !important; }` rewrites Chainlit’s header layout and separates the hamburger from the crescent control.
- [ ] Verify whether the injected button ends up in a hidden duplicate header while the visible header retains a different layout.

### Click Handling And Sidebar Toggle

- [ ] Inspect the live Chainlit 2.11.0 DOM and verify whether any of these selectors actually resolve to the sidebar:
  - `.cl-sidebar`
  - `[data-testid="sidebar"]`
  - `[data-sidebar]`
  - `.sidebar`
  - `#sidebar`
- [ ] Verify whether the sidebar is React-controlled and ignores manual `.classList.toggle('open')` and `.classList.toggle('closed')`.
- [ ] Verify whether `sidebar.toggle()` ever exists on the matched sidebar element.
- [ ] Verify whether `window.toggleSidebar` exists inside the iframe window.
- [ ] Verify whether the fallback selector `button[aria-label*="sidebar"], button[aria-label*="menu"]` matches `#ttt-hamburger-menu` itself and recursively clicks the custom button.
- [ ] Verify whether a native Chainlit sidebar button already exists and can be triggered directly instead of guessing sidebar classes.
- [ ] Verify whether the click event reaches the button or is blocked by overlay, z-index, stacking, or `pointer-events` issues.
- [ ] Verify whether the button is replaced by a new DOM node after render, leaving the visible node without the original click listener.
- [ ] Verify whether the `aria-expanded` state is lying because it is derived from guessed classes rather than actual sidebar state.

### Timing, Hydration, And Rerendering

- [ ] Verify whether custom JS runs before the final Chainlit header and sidebar mount, causing the button to be inserted into a temporary container.
- [ ] Verify whether React hydration remounts the header and invalidates the inserted button position.
- [ ] Verify whether the MutationObserver re-adds the button to different containers across rerenders.
- [ ] Verify whether the observer is masking a lifecycle bug by constantly re-inserting the button without preserving the correct target group.
- [ ] Verify whether the button position changes after the first response, theme change, or session switch.
- [ ] Verify whether the bug reproduces on both desktop-width and narrow-width layouts.

### CSS And Visual Layering

- [ ] Verify whether the generic `nav` and `header` CSS overrides in `public/workbench-chainlit.css` affect more than the intended Chainlit header.
- [ ] Verify whether Chainlit already applies layout rules to the visible header row that are now being overridden with `!important`.
- [ ] Verify whether the button is visually aligned in the DOM but offset by transforms, line-height, or inherited font metrics.
- [ ] Verify whether the button shares the same parent, baseline, and `align-items` context as the crescent control.
- [ ] Verify whether CSS from the outer workbench leaks into the iframe indirectly through shared asset assumptions or mistaken selector targeting during debugging.

### Asset Loading And Cache State

- [ ] Hard-refresh the browser and verify that the loaded `workbench-chainlit.js` contents match the repo copy.
- [ ] Hard-refresh the browser and verify that the loaded `workbench-chainlit.css` contents match the repo copy.
- [ ] Verify whether `custom_js = "/public/workbench-chainlit.js?v=4"` and `custom_css = "/public/workbench-chainlit.css?v=4"` are still serving stale cached assets in the local browser.
- [ ] Verify whether a cache-bust version bump is needed before trusting any UI change.

### Cross-Layer Debugging Traps

- [ ] Verify that any attempted fix is being made in the iframe assets in `public/`, not only in `src/ttt_workbench/templates/partials/chat_panel.html`.
- [ ] Verify that the outer workbench hamburger in `chat_panel.html` is not being mistaken for the broken Chainlit hamburger in the screenshot.
- [ ] Verify whether the outer chat panel or iframe container dimensions are visually exaggerating the position error even though the root bug is inside Chainlit.

### Regression Coverage

- [ ] Add a browser-level regression test that proves the custom hamburger renders in the same visible header group or row as the theme control.
- [ ] Add a browser-level regression test that clicking the custom hamburger opens or closes the sidebar.
- [ ] Add a regression test that the fallback click path never targets `#ttt-hamburger-menu` itself.
- [ ] Add a regression test or harness assertion for the specific live selectors used to find the header, theme control, and sidebar in the current Chainlit build.

## DevTools Probes To Run

Use the iframe DevTools console, not the parent workbench console.

```js
[...document.querySelectorAll('header, nav, [role="banner"]')].map((el, index) => ({
  index,
  tag: el.tagName,
  className: el.className,
  ariaLabel: el.getAttribute('aria-label'),
  rect: el.getBoundingClientRect().toJSON(),
  childCount: el.childElementCount
}))
```

```js
document.querySelector('#ttt-hamburger-menu')?.getBoundingClientRect()
```

```js
[...document.querySelectorAll('button')].map((el) => ({
  text: (el.textContent || '').trim(),
  ariaLabel: el.getAttribute('aria-label'),
  className: el.className
})).filter((row) => /theme|menu|sidebar|settings/i.test(`${row.text} ${row.ariaLabel} ${row.className}`))
```

```js
[
  '.cl-sidebar',
  '[data-testid="sidebar"]',
  '[data-sidebar]',
  '.sidebar',
  '#sidebar'
].map((selector) => ({ selector, match: !!document.querySelector(selector) }))
```

## Deliverables

1. Root-cause note documenting exactly why the hamburger is misaligned.
2. Root-cause note documenting exactly why the click path fails to open the sidebar.
3. A focused fix that places the button beside the crescent theme control in the correct visible header group.
4. A focused fix that toggles the actual Chainlit sidebar mechanism instead of guessing wrong state classes.
5. Browser-level regression coverage if feasible.
6. Manual verification notes for desktop and narrow layouts.

## Constraints

- Do not fix the wrong menu. The broken control in the screenshot is the Chainlit iframe hamburger, not the outer workbench chat menu.
- Do not ship a purely visual alignment tweak if the click path still uses the wrong sidebar mechanism.
- Do not rely on guessed `.open` and `.closed` classes unless verified against the live Chainlit DOM.
- Do not keep broad `nav` and `header` CSS overrides if they are the reason the layout drifts.
- Preserve the existing Chainlit custom copy-button behavior while working in `public/workbench-chainlit.js`.

## Verification Command

```bash
./ttt.sh web
```

Suggested regression check after the fix:

```bash
.venv/bin/python -m pytest tests/test_playwright_responsiveness.py -q
```

## Acceptance Criteria

- The custom hamburger is visually aligned with the crescent theme control in the live Chainlit header.
- The custom hamburger is inserted into the same visible control group as the crescent theme control, not merely on the same page.
- Clicking the hamburger opens and closes the correct Chainlit sidebar.
- The fallback path cannot recurse by clicking `#ttt-hamburger-menu` itself.
- Desktop and narrow-width layouts both keep the hamburger aligned and functional.
- Browser-level regression coverage exists if the test harness can exercise this UI reliably.
