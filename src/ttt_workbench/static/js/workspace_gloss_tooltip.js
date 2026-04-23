(function () {
  'use strict';

  var glossTipEl = null;
  var glossTipTimer = null;
  var glossTipHideTimer = null;

  function onGlossEnter(e) {
    clearTimeout(glossTipHideTimer);
    if (glossTipTimer) return;
    var el = e.target.closest('.gloss-word');
    if (!el) return;
    glossTipTimer = setTimeout(function () {
      glossTipTimer = null;
      showGlossTooltip(el, e);
    }, 350);
  }

  function onGlossLeave() {
    clearTimeout(glossTipTimer);
    glossTipTimer = null;
    glossTipHideTimer = setTimeout(hideGlossTooltip, 600);
  }

  function positionGlossTooltip(el) {
    if (!glossTipEl) return;
    var rect = el.getBoundingClientRect();
    var tipRect = glossTipEl.getBoundingClientRect();
    var x = rect.left;
    var y = rect.bottom + 6;
    if (x + tipRect.width > window.innerWidth - 10) x = window.innerWidth - tipRect.width - 10;
    if (y + tipRect.height > window.innerHeight - 10) y = rect.top - tipRect.height - 6;
    if (y < 10) y = 10;
    glossTipEl.style.left = x + 'px';
    glossTipEl.style.top = y + 'px';
  }

  function showGlossTooltip(el, e) {
    hideGlossTooltip();
    var surface = el.dataset.surface || '';
    var gloss = el.dataset.gloss || '';
    var isHeb = el.closest('.chunk-block-body') ? el.closest('.chunk-block-body').classList.contains('hebrew') : false;
    glossTipEl = document.createElement('div');
    glossTipEl.className = 'gloss-tooltip';
    var surfaceEl = document.createElement('div');
    surfaceEl.className = 'gloss-tooltip-surface' + (isHeb ? ' hebrew' : '');
    surfaceEl.textContent = surface;
    var metaEl = document.createElement('div');
    metaEl.className = 'gloss-tooltip-meta';
    var glossEl = document.createElement('span');
    glossEl.className = 'gloss-tooltip-gloss';
    glossEl.textContent = gloss;
    var copyBtn = document.createElement('button');
    copyBtn.className = 'gloss-tooltip-copy';
    copyBtn.type = 'button';
    copyBtn.textContent = 'Copy';
    copyBtn.addEventListener('click', function () {
      copyGlossWord(copyBtn, surface);
    });
    metaEl.appendChild(glossEl);
    metaEl.appendChild(copyBtn);
    glossTipEl.appendChild(surfaceEl);
    glossTipEl.appendChild(metaEl);
    glossTipEl.addEventListener('mouseenter', function () { clearTimeout(glossTipHideTimer); });
    glossTipEl.addEventListener('mouseleave', function () {
      glossTipHideTimer = setTimeout(hideGlossTooltip, 300);
    });
    document.body.appendChild(glossTipEl);
    positionGlossTooltip(el);
  }

  function hideGlossTooltip() {
    clearTimeout(glossTipHideTimer);
    if (glossTipEl) { glossTipEl.remove(); glossTipEl = null; }
  }

  function copyGlossWord(btn, text) {
    writeClipboardText(text).then(function () {
      btn.textContent = '✓';
      sessionStorage.setItem('lastGlossCopied', text);
      try { showGlossCopiedIndicator(text); } catch (err) { console.warn('Copied indicator failed', err); }
      setTimeout(function () { btn.textContent = 'Copy'; }, 1200);
    }, function () {
      btn.textContent = 'Failed';
    });
  }

  function showGlossCopiedIndicator(text) {
    window.showWorkspaceIndicator('Copied: ' + text.substring(0, 30) + (text.length > 30 ? '…' : ''));
  }

  function initGlossTooltips() {
    document.querySelectorAll('.gloss-word').forEach(function (el) {
      el.removeEventListener('mouseenter', onGlossEnter);
      el.removeEventListener('mouseleave', onGlossLeave);
      el.addEventListener('mouseenter', onGlossEnter);
      el.addEventListener('mouseleave', onGlossLeave);
    });
  }

  function writeClipboardText(text) {
    var value = String(text || '');
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      return navigator.clipboard.writeText(value).catch(function () {
        return fallbackWriteClipboardText(value);
      });
    }
    return fallbackWriteClipboardText(value);
  }

  function fallbackWriteClipboardText(text) {
    return new Promise(function (resolve, reject) {
      var textarea = document.createElement('textarea');
      textarea.value = String(text);
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.left = '-9999px';
      textarea.style.top = '0';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      try {
        var ok = document.execCommand('copy');
        textarea.remove();
        ok ? resolve() : reject(new Error('Copy command failed.'));
      } catch (err) {
        textarea.remove();
        reject(err);
      }
    });
  }

  window.glossTipEl = glossTipEl;
  window.showGlossTooltip = showGlossTooltip;
  window.hideGlossTooltip = hideGlossTooltip;
  window.showGlossCopiedIndicator = showGlossCopiedIndicator;
  window.writeClipboardText = writeClipboardText;
  window.initGlossTooltips = initGlossTooltips;
  window.fallbackWriteClipboardText = fallbackWriteClipboardText;
})();