# 006 Editorial Enhancement and Support Entry Editing

## Objective

Improve the browser workbench so editors can revise existing justifications and footnotes in place, and add an isolated editorial enhancement surface that uses targeted model prompts for controlled line-level improvements.

## Why

The current browser support panels allow adding justifications and footnotes, but not editing existing saved or pending entries. The drafting workflow also lacks a focused editorial assistant for small, deliberate wording improvements that should not be mixed into the main chat thread.

## Scope

- Add browser editing support for existing justification entries
- Add browser editing support for existing footnote entries
- Replace justification autofill with a more general custom enhancement path
- Add an isolated editorial enhancement article below chat
- Support three enhancement modes with editable prompts:
  1. grammar and English correctness only
  2. concise rewrite without information loss
  3. scholarly professional rephrase
- Add small inline enhancement buttons to draft verse rows for modes 1 and 2
- Add small inline enhancement buttons to support composers for mode 3 and custom prompt use
- Keep enhancement results separate from chat history unless explicitly applied

## Prompt Requirements

1. Grammar-only prompt
   - Correct grammar, spelling, punctuation, and natural English only
   - Preserve wording, structure, and intent as much as possible
   - Change sentence structure only when the original is clearly unacceptable English

2. Concision prompt
   - Return a shorter version with the same meaning
   - Do not remove information or theological nuance
   - Keep the tone neutral and editorially usable

3. Scholarly prompt
   - Rephrase the sentence in a scholarly, professional editorial tone
   - Preserve intent and factual content
   - Make it suitable for footnotes and justification prose

4. Custom prompt
   - Let the user supply an arbitrary instruction for the current text
   - Return only the revised text requested by the user

## Deliverables

1. Edit actions for saved and pending justifications
2. Edit actions for saved and pending footnotes
3. A new browser article dedicated to editorial enhancement, separate from chat
4. Editable default prompts for the three predefined enhancement modes
5. A copyable enhancement output area
6. Inline enhancement controls on draft verse rows for grammar-only and concision
7. Inline enhancement controls on justification and footnote composers for scholarly and custom enhancement
8. Removal of the old justification autofill button in favor of the new enhancement workflow

## Constraints

- Do not merge editorial enhancement traffic into the normal chat conversation
- Do not silently overwrite user content without an explicit apply action
- Keep the inline controls compact and understandable through symbols plus tooltips
- Preserve existing JSON schemas and commit behavior
- Reuse the existing local model endpoint and browser controller architecture

## Acceptance Criteria

- Existing saved justifications can be loaded into the composer, edited, and re-staged without manual recreation
- Existing saved footnotes can be loaded into the composer, edited, and re-staged without manual recreation
- The editorial enhancement article can accept text, run one of the three preset modes or a custom prompt, and return copyable output
- Prompt text for each preset mode can be viewed and edited by the user
- Draft verse rows expose compact grammar-only and concision actions that can replace the same verse field with the model output
- Justification and footnote composers expose scholarly and custom enhancement actions
- The support composer no longer depends on the old autofill-specific justification flow
