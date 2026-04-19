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
    return normalizeCopiedText(domText(clone, { orderedStack: [] }));
  }

  function normalizeCopiedText(text) {
    return String(text || '')
      .replace(/\r\n/g, '\n')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n[ \t]+/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function domText(node, state) {
    state = state || { orderedStack: [] };
    if (!node) return '';
    if (node.nodeType === Node.TEXT_NODE) {
      return node.nodeValue || '';
    }
    if (node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) {
      return '';
    }

    var tag = node.nodeType === Node.ELEMENT_NODE ? node.tagName.toLowerCase() : '';
    if (tag === 'br') return '\n';
    if (tag === 'script' || tag === 'style' || tag === 'svg') return '';
    if (tag === 'pre') return '\n' + (node.innerText || node.textContent || '') + '\n';
    if (tag === 'code' && node.closest && node.closest('pre')) {
      return node.textContent || '';
    }
    if (tag === 'ol') {
      state.orderedStack.push(1);
      var ordered = childrenText(node, state);
      state.orderedStack.pop();
      return blockText(ordered);
    }
    if (tag === 'ul') {
      state.orderedStack.push(null);
      var unordered = childrenText(node, state);
      state.orderedStack.pop();
      return blockText(unordered);
    }
    if (tag === 'li') {
      var marker = '- ';
      var top = state.orderedStack.length ? state.orderedStack[state.orderedStack.length - 1] : null;
      if (typeof top === 'number') {
        marker = top + '. ';
        state.orderedStack[state.orderedStack.length - 1] = top + 1;
      }
      return marker + normalizeLineText(childrenText(node, state)) + '\n';
    }

    var text = childrenText(node, state);
    if (isBlockElement(tag)) return blockText(text);
    return text;
  }

  function childrenText(node, state) {
    return Array.prototype.map.call(node.childNodes || [], function (child) {
      if (child.nodeType === Node.TEXT_NODE && !String(child.nodeValue || '').trim() && node.children && node.children.length) {
        return '';
      }
      return domText(child, state);
    }).join('');
  }

  function normalizeLineText(text) {
    return String(text || '').replace(/\s*\n\s*/g, ' ').replace(/[ \t]{2,}/g, ' ').trim();
  }

  function blockText(text) {
    text = String(text || '').trim();
    return text ? text + '\n\n' : '';
  }

  function isBlockElement(tag) {
    return [
      'address', 'article', 'aside', 'blockquote', 'div', 'dl', 'fieldset', 'figcaption',
      'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hr',
      'main', 'nav', 'p', 'section', 'table'
    ].indexOf(tag) !== -1;
  }

  function addCopyButton(container) {
    if (!container) return;
    applyUserPromptClass(container);
    if (container.dataset.tttCopyBound === '1') return;
    var text = messageText(container);
    if (!text || text.length < 2) return;
    container.dataset.tttCopyBound = '1';
    container.classList.add('ttt-chainlit-copy-host');
    applyUserPromptClass(container);

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

  function applyUserPromptClass(container) {
    var messageFrame = container.closest('[data-step-type]');
    if (messageFrame) {
      messageFrame.classList.add('ttt-chainlit-message-frame');
      if (messageFrame.getAttribute('data-step-type') === 'user_message') {
        container.classList.add('ttt-chainlit-user-prompt');
      }
    }
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

  window.TTTChainlitCopy = {
    messageText: messageText
  };
}());
