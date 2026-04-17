(function () {
  'use strict';

  function call(name) {
    if (typeof window[name] === 'function') {
      window[name]();
    }
  }

  function autoResizeTextareas() {
    if (typeof window.autoResize !== 'function') return;
    document.querySelectorAll('textarea').forEach(function (el) {
      window.autoResize(el);
    });
  }

  function refreshBoundTextareaHeights() {
    requestAnimationFrame(function () {
      document.querySelectorAll('textarea').forEach(function (el) {
        if (!el.dataset.autoResizeBound) return;
        el.style.height = 'auto';
        el.style.height = el.scrollHeight + 'px';
      });
    });
  }

  function restoreStudyControls() {
    var studyBlocks = document.getElementById('study-blocks');
    if (!studyBlocks) return;
    var fontSize = localStorage.getItem('studyFontSize') || '16';
    if (typeof window.applyStudyFontSize === 'function') {
      window.applyStudyFontSize(fontSize);
    }
    var sizeSelect = document.getElementById('study-font-size');
    if (sizeSelect) sizeSelect.value = fontSize;

    var verseFilterValue = localStorage.getItem('studyVerseFilter') || '';
    var verseFilter = document.getElementById('study-verse-filter');
    if (verseFilter) verseFilter.value = verseFilterValue;
    if (verseFilterValue && typeof window.applyStudyVerseFilter === 'function') {
      window.applyStudyVerseFilter();
    }
  }

  function restoreChatScroll() {
    var chatLog = document.querySelector('.chat-log');
    if (chatLog) chatLog.scrollTop = chatLog.scrollHeight;
  }

  function restoreGlossCopiedIndicator() {
    var lastCopied = sessionStorage.getItem('lastGlossCopied');
    if (!lastCopied) return;
    if (typeof window.showGlossCopiedIndicator === 'function') {
      window.showGlossCopiedIndicator(lastCopied);
    }
    sessionStorage.removeItem('lastGlossCopied');
  }

  function initWorkspace() {
    autoResizeTextareas();
    refreshBoundTextareaHeights();
    restoreStudyControls();
    call('initGlossTooltips');
    call('initSupportFormattingTools');
    call('initModelActionForms');
    call('initPromptEngineering');
    call('initChatInput');
    call('initEditorAutosave');
    restoreChatScroll();
    restoreGlossCopiedIndicator();
  }

  document.addEventListener('DOMContentLoaded', initWorkspace);
  document.addEventListener('htmx:afterSettle', initWorkspace);

  window.TTTWorkspaceBootstrap = {
    init: initWorkspace,
  };
}());
