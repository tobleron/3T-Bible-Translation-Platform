(function () {
  'use strict';

  function showWorkspaceIndicator(message, tone) {
    if (window.TTTInteractions && window.TTTInteractions.toast) {
      window.TTTInteractions.toast(message, tone || 'info');
      return;
    }
    var indicator = document.getElementById('workspaceToast');
    if (!indicator) return;
    indicator.className = 'workspace-toast is-visible is-' + (tone || 'info');
    indicator.textContent = message;
    clearTimeout(showWorkspaceIndicator._timer);
    showWorkspaceIndicator._timer = setTimeout(function () {
      indicator.classList.remove('is-visible');
    }, 3000);
  }

  window.showWorkspaceIndicator = showWorkspaceIndicator;
})();