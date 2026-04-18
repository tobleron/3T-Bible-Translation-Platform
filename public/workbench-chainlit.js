(function () {
  'use strict';

  var COPY_BUTTON_CLASS = 'ttt-chainlit-copy-button';
  var COPIED_CLASS = 'ttt-chainlit-copy-copied';

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
      textarea.value = String(text || '');
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

  function messageText(container) {
    var clone = container.cloneNode(true);
    clone.querySelectorAll('.' + COPY_BUTTON_CLASS + ', button, textarea, input, select').forEach(function (el) {
      el.remove();
    });
    return (clone.innerText || clone.textContent || '').trim();
  }

  function addCopyButton(container) {
    if (!container || container.dataset.tttCopyBound === '1') return;
    var text = messageText(container);
    if (!text || text.length < 2) return;
    container.dataset.tttCopyBound = '1';
    container.classList.add('ttt-chainlit-copy-host');

    var button = document.createElement('button');
    button.type = 'button';
    button.className = COPY_BUTTON_CLASS;
    button.textContent = 'Copy';
    button.title = 'Copy message';
    button.setAttribute('aria-label', 'Copy message');
    button.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      writeClipboardText(messageText(container)).then(function () {
        button.textContent = 'Copied';
        button.classList.add(COPIED_CLASS);
        setTimeout(function () {
          button.textContent = 'Copy';
          button.classList.remove(COPIED_CLASS);
        }, 1400);
      }, function () {
        button.textContent = 'Failed';
        setTimeout(function () {
          button.textContent = 'Copy';
        }, 1800);
      });
    });
    container.appendChild(button);
  }

  function candidateMessages() {
    var selectors = [
      '[data-step-type]',
      '[data-test*="message"]',
      '[class*="message"]'
    ];
    var nodes = Array.prototype.slice.call(document.querySelectorAll(selectors.join(',')));
    return nodes.filter(function (node) {
      if (!(node instanceof HTMLElement)) return false;
      if (node.closest('form, nav, header, footer')) return false;
      if (node.querySelector('.' + COPY_BUTTON_CLASS)) return false;
      var text = messageText(node);
      if (!text || text.length < 2) return false;
      return !nodes.some(function (other) {
        return other !== node && other.contains(node) && messageText(other).length <= text.length + 80;
      });
    });
  }

  function enhanceMessages() {
    candidateMessages().forEach(addCopyButton);
  }

  function start() {
    enhanceMessages();
    var observer = new MutationObserver(function () {
      window.requestAnimationFrame(enhanceMessages);
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
}());
