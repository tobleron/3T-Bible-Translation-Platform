(function () {
  'use strict';

  var COPY_BUTTON_CLASS = 'ttt-chainlit-copy-button';
  var COPIED_CLASS = 'ttt-chainlit-copy-copied';
  var COPY_ICON = '\u29c9';
  var COPIED_ICON = '\u2713';

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
    var messageFrame = container.closest('[data-step-type]');
    if (messageFrame) {
      messageFrame.classList.add('ttt-chainlit-message-frame');
      if (messageFrame.getAttribute('data-step-type') === 'user_message') {
        container.classList.add('ttt-chainlit-user-prompt');
      }
    }

    var button = document.createElement('button');
    button.type = 'button';
    button.className = COPY_BUTTON_CLASS;
    button.textContent = COPY_ICON;
    button.title = 'Copy message';
    button.setAttribute('aria-label', 'Copy message');
    button.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      writeClipboardText(messageText(container)).then(function () {
        button.textContent = COPIED_ICON;
        button.classList.add(COPIED_CLASS);
        setTimeout(function () {
          button.textContent = COPY_ICON;
          button.classList.remove(COPIED_CLASS);
        }, 1400);
      }, function () {
        button.textContent = '!';
        setTimeout(function () {
          button.textContent = COPY_ICON;
        }, 1800);
      });
    });
    container.appendChild(button);
  }

  function candidateMessages() {
    var selectors = [
      '[data-step-type]',
      '[data-test*="message"]'
    ];
    var nodes = Array.prototype.slice.call(document.querySelectorAll(selectors.join(',')));
    nodes = nodes.map(function (node) {
      return messageBodyHost(node);
    }).filter(Boolean);
    return Array.from(new Set(nodes)).filter(function (node) {
      if (!(node instanceof HTMLElement)) return false;
      if (node.closest('form, nav, header, footer')) return false;
      if (node.querySelector('.' + COPY_BUTTON_CLASS)) return false;
      var text = messageText(node);
      if (!text || text.length < 2) return false;
      return true;
    });
  }

  function messageBodyHost(node) {
    var frame = node.matches('[data-step-type]') ? node : node.closest('[data-step-type]');
    if (frame && frame.getAttribute('data-step-type') === 'user_message') {
      var userBubble = frame.querySelector('.bg-accent.rounded-3xl')
        || frame.querySelector('[class*="bg-accent"][class*="rounded-"]');
      if (userBubble && messageText(userBubble).length >= 2) return userBubble;
    }

    var bodySelectors = [
      '.markdown-body',
      '[class*="markdown"]',
      '[data-testid*="content"]',
      '[data-test*="content"]'
    ];
    for (var i = 0; i < bodySelectors.length; i += 1) {
      var body = node.querySelector(bodySelectors[i]);
      if (body && messageText(body).length >= 2) return body;
    }
    if (node.children.length === 1 && messageText(node.firstElementChild).length >= 2) {
      return node.firstElementChild;
    }
    return node;
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
