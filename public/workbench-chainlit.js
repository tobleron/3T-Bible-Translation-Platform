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
    if (!container.classList.contains('ttt-chainlit-user-prompt')) return;
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

  function removeNonUserCopyButtons() {
    document.querySelectorAll('.' + COPY_BUTTON_CLASS).forEach(function (button) {
      if (!button.closest('.ttt-chainlit-user-prompt')) {
        button.remove();
      }
    });
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

   function addHamburgerMenu() {
     if (document.getElementById('ttt-hamburger-menu')) return;

     // Find Chainlit header - try multiple selectors
     var header = document.querySelector('.cl-header') ||
                  document.querySelector('[data-testid="cl-header"]') ||
                  document.querySelector('nav') ||
                  document.querySelector('header') ||
                  document.querySelector('[role="banner"]');

     if (!header) {
       // Debug: log available header-like elements
       console.log('TTT: Available headers:', document.querySelectorAll('header, nav, [role="banner"], [data-testid*="header"], .header'));
       console.log('TTT: All top-level elements:', document.querySelectorAll('body > *'));
       return;
     }

     console.log('TTT: Found header:', header);
     console.log('TTT: Header class:', header.className);
     console.log('TTT: Header children:', header.children);

     // Look for existing theme/settings controls to position our hamburger menu similarly
     var themeControl = document.querySelector('[aria-label*="theme"], [aria-label*="Theme"], [data-testid*="theme"], .cl-theme-select, .cl-settings-toggle');
     var settingsControl = document.querySelector('[aria-label*="settings"], [aria-label*="Settings"], [data-testid*="settings"]');

     // Create hamburger button
     var hamburgerBtn = document.createElement('button');
     hamburgerBtn.id = 'ttt-hamburger-menu';
     hamburgerBtn.type = 'button';
     hamburgerBtn.className = 'ttt-hamburger-btn';
     hamburgerBtn.title = 'Toggle sidebar';
     hamburgerBtn.setAttribute('aria-label', 'Toggle sidebar');
     hamburgerBtn.setAttribute('aria-expanded', 'false');

     hamburgerBtn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>';

     // Position the hamburger menu to appear at the same level as theme/settings controls
     // Try to insert it before the first theme or settings control we find, or at the beginning
     var insertBefore = themeControl || settingsControl || header.firstChild;
     
     if (insertBefore && insertBefore.parentNode === header) {
       header.insertBefore(hamburgerBtn, insertBefore);
     } else {
       // Fallback: insert at the beginning
       header.insertBefore(hamburgerBtn, header.firstChild);
     }

     hamburgerBtn.addEventListener('click', function(e) {
       e.preventDefault();
       e.stopPropagation();

       // Try multiple selectors for Chainlit sidebar
       var sidebar = document.querySelector('.cl-sidebar') ||
                    document.querySelector('[data-testid="sidebar"]') ||
                    document.querySelector('[data-sidebar]') ||
                    document.querySelector('.sidebar') ||
                    document.querySelector('#sidebar');

       if (sidebar) {
         // Check if sidebar has a toggle method or class-based toggle
         if (typeof sidebar.toggle === 'function') {
           sidebar.toggle();
         } else {
           sidebar.classList.toggle('open');
           sidebar.classList.toggle('closed');
         }
         var isOpen = sidebar.classList.contains('open') || !sidebar.classList.contains('closed');
         hamburgerBtn.setAttribute('aria-expanded', isOpen);
       } else if (typeof window.toggleSidebar === 'function') {
         window.toggleSidebar();
       } else {
         // Fallback: try clicking any existing hamburger menu
         var existingMenu = document.querySelector('button[aria-label*="sidebar"], button[aria-label*="menu"]');
         if (existingMenu) {
           existingMenu.click();
         } else {
           console.warn('TTT: Could not find Chainlit sidebar to toggle.');
         }
       }
     });

      console.log('TTT: Hamburger menu added successfully');
    }

  function candidateMessages() {
    var nodes = Array.prototype.slice.call(document.querySelectorAll('[data-step-type="user_message"]'));
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
      return null;
    }
    return null;
  }

  function enhanceMessages() {
    removeNonUserCopyButtons();
    candidateMessages().forEach(addCopyButton);
  }

  function start() {
    enhanceMessages();
    addHamburgerMenu();

    var observer = new MutationObserver(function () {
      window.requestAnimationFrame(function() {
        enhanceMessages();
        addHamburgerMenu();
      });
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
