(function () {
  'use strict';

  function parseVerseSpec(spec) {
    var verses = [];
    var parts = spec.split(',');
    for (var i = 0; i < parts.length; i++) {
      var part = parts[i].trim();
      if (!part) continue;
      if (part.indexOf('-') !== -1) {
        var dashIdx = part.indexOf('-');
        var start = parseInt(part.substring(0, dashIdx).trim(), 10);
        var end = parseInt(part.substring(dashIdx + 1).trim(), 10);
        if (!isNaN(start) && !isNaN(end) && start > 0 && end > 0) {
          var lo = Math.min(start, end), hi = Math.max(start, end);
          for (var v = lo; v <= hi; v++) verses.push(v);
        }
      } else {
        var v = parseInt(part, 10);
        if (!isNaN(v) && v > 0) verses.push(v);
      }
    }
    return verses;
  }

  function applyStudyVerseFilter() {
    var input = document.getElementById('study-verse-filter');
    if (!input) return;
    var spec = input.value.trim();
    if (!spec) { clearStudyVerseFilter(); return; }
    localStorage.setItem('studyVerseFilter', spec);
    var allowed = parseVerseSpec(spec);
    if (allowed.length === 0) return;
    var allowedSet = {};
    for (var i = 0; i < allowed.length; i++) allowedSet[allowed[i]] = true;

    var sheet = document.getElementById('study-blocks');
    if (!sheet) return;
    var chunkStart = parseInt(sheet.getAttribute('data-chunk-start') || '0', 10);
    var chunkEnd = parseInt(sheet.getAttribute('data-chunk-end') || '0', 10);

    var blocks = sheet.querySelectorAll('.chunk-block');
    for (var i = 0; i < blocks.length; i++) {
      var block = blocks[i];
      if (block.classList.contains('translation-block')) {
        var verseRows = block.querySelectorAll('.translation-verse-row');
        var anyVisible = false;
        for (var j = 0; j < verseRows.length; j++) {
          var vr = verseRows[j];
          var vNum = parseInt(vr.getAttribute('data-verse') || '0', 10);
          var show = (vNum in allowedSet);
          vr.style.display = show ? '' : 'none';
          if (show) anyVisible = true;
        }
        block.style.display = anyVisible ? '' : 'none';
      } else {
        var verseRows = block.querySelectorAll('.translation-verse-row[data-verse]');
        var showBlock = false;
        for (var j = 0; j < verseRows.length; j++) {
          var vr = verseRows[j];
          var vNum = parseInt(vr.getAttribute('data-verse') || '0', 10);
          var show = (vNum in allowedSet);
          vr.style.display = show ? '' : 'none';
          if (show) showBlock = true;
        }
        block.style.display = showBlock ? '' : 'none';
      }
    }
    document.querySelectorAll('#study-word-analysis .word-analysis-verse[data-verse]').forEach(function (verseBlock) {
      var vNum = parseInt(verseBlock.getAttribute('data-verse') || '0', 10);
      verseBlock.style.display = (vNum in allowedSet) ? '' : 'none';
    });
    if (typeof window.syncPromptEngineeringDraftAvailability === 'function') {
      window.syncPromptEngineeringDraftAvailability();
    }
    if (typeof window.updatePromptEngineeringPreview === 'function') {
      window.updatePromptEngineeringPreview();
    }
  }

  function clearStudyVerseFilter() {
    var input = document.getElementById('study-verse-filter');
    if (input) input.value = '';
    localStorage.removeItem('studyVerseFilter');
    var sheet = document.getElementById('study-blocks');
    if (!sheet) return;
    var blocks = sheet.querySelectorAll('.chunk-block');
    for (var i = 0; i < blocks.length; i++) {
      blocks[i].style.display = '';
      var verseRows = blocks[i].querySelectorAll('.translation-verse-row');
      for (var j = 0; j < verseRows.length; j++) {
        verseRows[j].style.display = '';
      }
    }
    document.querySelectorAll('#study-word-analysis .word-analysis-verse[data-verse]').forEach(function (verseBlock) {
      verseBlock.style.display = '';
    });
    if (typeof window.syncPromptEngineeringDraftAvailability === 'function') {
      window.syncPromptEngineeringDraftAvailability();
    }
    if (typeof window.updatePromptEngineeringPreview === 'function') {
      window.updatePromptEngineeringPreview();
    }
  }

  document.addEventListener('change', function (e) {
    if (e.target.id === 'study-font-size') {
      localStorage.setItem('studyFontSize', e.target.value);
      applyStudyFontSize(e.target.value);
    }
  });

  function applyStudyFontSize(px) {
    var el = document.getElementById('study-blocks');
    if (el) {
      el.style.fontSize = px + 'px';
      el.querySelectorAll('.chunk-block-body, .chunk-block-gloss, .translation-verse-text, .translation-verse-num, .lexical-summary').forEach(function (b) { b.style.fontSize = px + 'px'; });
    }
    var analysis = document.getElementById('study-word-analysis');
    if (analysis) {
      analysis.style.fontSize = px + 'px';
      analysis.querySelectorAll('.word-choice-line, .word-stat-label').forEach(function (b) { b.style.fontSize = px + 'px'; });
      analysis.querySelectorAll('.word-choice-sources').forEach(function (b) { b.style.fontSize = Math.max(10, Math.round(parseInt(px, 10) * 0.86)) + 'px'; });
    }
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (typeof window.hideJsonPreview === 'function') window.hideJsonPreview();
      if (typeof window.hideGlossTooltip === 'function') window.hideGlossTooltip();
    }
    if (e.key === 'Enter' && e.target && e.target.id === 'study-verse-filter') {
      e.preventDefault();
      applyStudyVerseFilter();
    }
  });

  window.parseVerseSpec = parseVerseSpec;
  window.applyStudyVerseFilter = applyStudyVerseFilter;
  window.clearStudyVerseFilter = clearStudyVerseFilter;
  window.applyStudyFontSize = applyStudyFontSize;
})();