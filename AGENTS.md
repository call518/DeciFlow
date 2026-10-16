# Documentation and environment maintenance

- When creating or updating `AGENTS.md`, never include secrets, credentials,
  sensitive internal information, or personal data. Use placeholders when
  examples are needed.

- Keep project UI and code messages in English by default.

- Use Title Case for static UI titles, including page/section/form/dialog headings,
  result-card and metric titles, table/field labels, and button captions. Keep
  short articles, conjunctions, and prepositions lowercase unless first or last
  (e.g. "Sources and Decisions", "Back to List"). Preserve acronyms and technical
  identifiers (SSH, JSON, Python, venv), and never recase user-defined names or data.
  Keep descriptions, help text, tooltips, and status sentences in sentence case.
  Write the intended casing in the UI strings rather than using CSS text-transform;
  update matching tests and English/Korean documentation labels together.

- Write release notes in English, keeping them concise and clear and focused on
  key changes. Provide them in a fenced `markdown` code block for copy and paste.

- Update `README.md` in English and `README.ko.md` in Korean together. Keep their
  features, settings, commands, and limitations equivalent.

- Keep READMEs concise and clear without omitting essential information. Remove
  repetition and unnecessary explanations, and format commands for readability.
  When multiple execution methods exist, state whether users choose one or combine
  them, and distinguish each method's requirements and steps explicitly.

- Define DeciFlow, the Laya server, and the Jev service before describing their
  interactions. Name the application or host explicitly when giving requirements,
  settings, or commands; avoid undefined labels such as "remote client" or "server".

- Document each environment setting with both English and Korean comments.

- When changing `.env.example` (or `.env.template`, if introduced), apply the same
  setting and comment changes to the actual `.env`. Preserve existing secret values
  and user settings unless their modification is explicitly requested. Never print
  or commit secrets.
  
- Maintain Laya and Jev together: share classification criteria, result validation,
  source handling, and UI behavior. Test both engines for provider changes.
  Laya is the default; never fall back automatically to the paid Jev API.

# UI consistency and space efficiency

- When changing a UI pattern, inspect all screens using the same pattern and apply
  the improvement consistently within the authorized scope. Do not fix only the
  example screen and leave equivalent Views, lists, or dialogs inconsistent.
  Reuse shared rendering helpers and styles instead of duplicating per-screen UI.

- Keep equivalent information at the same visual level. Task assignments such as
  Source, Criteria, Action, and target Hosts must not appear subordinate to a
  Source name. Avoid repeated titles, redundant navigation buttons, and wrappers
  that add space without clarifying structure.

- Use compact label/value layouts for every read-only View, not disabled inputs
  or oversized textareas. Place short values side by side when space permits;
  wrap long values and stack fields on narrow screens. Allocate extra space only
  for content that needs it, such as code or public keys. Avoid fixed minimum
  heights, excessive padding, and empty space that creates unnecessary scrolling.
  Keep editable forms distinct from read-only Views.

- Expand list details directly below the selected row and preserve that placement
  through list refreshes. Use shared in-app dialogs for confirmations and blockers,
  never native browser alerts or confirmations. View toggles and redraws must not
  trigger unrelated network checks or other side effects.

- Verify representative affected screens, long values, and narrow layouts before
  reporting a UI consistency change complete. Test shared behavior and use an
  actual browser to check layout; passing DOM tests alone does not establish
  visual consistency.
