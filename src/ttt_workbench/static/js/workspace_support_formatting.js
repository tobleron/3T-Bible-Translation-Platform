(function () {
  'use strict';

  function findSupportFormatField(trigger) {
    var form = trigger.closest('form');
    if (!form) return null;
    var active = document.activeElement;
    if (active && form.contains(active) && active.matches('[data-inline-format-field]')) {
      return active;
    }
    return form.querySelector('[data-inline-format-default]') || form.querySelector('[data-inline-format-field]');
  }

  function applySupportFormat(trigger, kind) {
    var field = findSupportFormatField(trigger);
    if (!field || typeof field.value !== 'string') return;

    var wrapOpen = '';
    var wrapClose = '';
    var placeholder = '';
    var insertText = '';

    if (kind === 'italic') {
      wrapOpen = '<i>';
      wrapClose = '</i>';
      placeholder = 'text';
    } else if (kind === 'bold') {
      wrapOpen = '<strong>';
      wrapClose = '</strong>';
      placeholder = 'text';
    } else {
      return;
    }

    var start = typeof field.selectionStart === 'number' ? field.selectionStart : field.value.length;
    var end = typeof field.selectionEnd === 'number' ? field.selectionEnd : field.value.length;
    var before = field.value.slice(0, start);
    var selected = field.value.slice(start, end);
    var after = field.value.slice(end);
    var replacement = insertText;
    var selectionStart = start;
    var selectionEnd = start;

    if (!insertText) {
      var body = selected || placeholder;
      replacement = wrapOpen + body + wrapClose;
      if (selected) {
        selectionStart = start + replacement.length;
        selectionEnd = selectionStart;
      } else {
        selectionStart = start + wrapOpen.length;
        selectionEnd = selectionStart + body.length;
      }
    } else {
      selectionStart = start + replacement.length;
      selectionEnd = selectionStart;
    }

    field.value = before + replacement + after;
    field.focus();
    if (typeof field.setSelectionRange === 'function') {
      field.setSelectionRange(selectionStart, selectionEnd);
    }
    field.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function escapeSupportHtml(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function normalizeSupportInlineMarkup(text) {
    return String(text || '')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .replace(/(?<!\*)\*\*([^*\n][^*]*?)\*\*(?!\*)/g, '<strong>$1</strong>')
      .replace(/(?<!\*)\*([^*\n][^*]*?)\*(?!\*)/g, '<em>$1</em>')
      .replace(/\n/g, '<br>');
  }

  function sanitizeSupportInlineMarkup(text) {
    var normalized = normalizeSupportInlineMarkup(text);
    var doc = new DOMParser().parseFromString('<div>' + normalized + '</div>', 'text/html');
    var allowed = { i: true, em: true, b: true, strong: true, sup: true, sub: true, br: true };
    var blocked = { script: true, style: true };

    function renderNode(node) {
      if (node.nodeType === Node.TEXT_NODE) {
        return escapeSupportHtml(node.textContent || '');
      }
      if (node.nodeType !== Node.ELEMENT_NODE) {
        return '';
      }
      var tag = node.tagName.toLowerCase();
      if (blocked[tag]) {
        return '';
      }
      if (tag === 'br' && allowed[tag]) {
        return '<br>';
      }
      var inner = '';
      Array.prototype.forEach.call(node.childNodes, function (child) {
        inner += renderNode(child);
      });
      if (!allowed[tag]) {
        return inner;
      }
      return '<' + tag + '>' + inner + '</' + tag + '>';
    }

    var root = doc.body.firstElementChild;
    if (!root) return '';
    var html = '';
    Array.prototype.forEach.call(root.childNodes, function (child) {
      html += renderNode(child);
    });
    return html;
  }

  function plainSupportInlineMarkup(text) {
    var container = document.createElement('div');
    container.innerHTML = sanitizeSupportInlineMarkup(text);
    return (container.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function syncSupportComposerPreview(form) {
    if (!form) return;
    form.querySelectorAll('[data-inline-preview-panel]').forEach(function (panel) {
      var sourceName = panel.getAttribute('data-preview-source');
      var source = sourceName ? form.querySelector('[name="' + sourceName + '"]') : null;
      var htmlTarget = panel.querySelector('[data-inline-preview-html]');
      if (!source || !htmlTarget) return;
      var previewHtml = sanitizeSupportInlineMarkup(source.value || '');
      if (!plainSupportInlineMarkup(source.value || '')) {
        panel.hidden = true;
        htmlTarget.innerHTML = '';
        return;
      }
      htmlTarget.innerHTML = previewHtml;
      panel.hidden = false;
    });
  }

  function initSupportFormattingTools() {
    document.querySelectorAll('.support-form').forEach(function (form) {
      if (form.dataset.inlinePreviewBound === '1') {
        syncSupportComposerPreview(form);
        return;
      }
      form.dataset.inlinePreviewBound = '1';
      form.querySelectorAll('[data-inline-format-field]').forEach(function (field) {
        field.addEventListener('input', function () {
          syncSupportComposerPreview(form);
        });
      });
      syncSupportComposerPreview(form);
    });
  }

  window.findSupportFormatField = findSupportFormatField;
  window.applySupportFormat = applySupportFormat;
  window.escapeSupportHtml = escapeSupportHtml;
  window.normalizeSupportInlineMarkup = normalizeSupportInlineMarkup;
  window.sanitizeSupportInlineMarkup = sanitizeSupportInlineMarkup;
  window.plainSupportInlineMarkup = plainSupportInlineMarkup;
  window.syncSupportComposerPreview = syncSupportComposerPreview;
  window.initSupportFormattingTools = initSupportFormattingTools;
})();