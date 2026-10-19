# Development stage and compatibility policy

- This project is in early development. Prioritize clean, clear, and efficient
  implementations of current requirements. Compatibility with previous logic,
  features, APIs, configuration formats, or stored data is not a requirement.
- Within the requested scope, remove obsolete compatibility code rather than
  preserving it. Do not add aliases, adapters, fallbacks, migrations, or data
  converters solely to support previous versions.
- Preserve the correctness of current features, validation, and safety mechanisms.
  Better logic may replace existing implementations; update affected callers,
  tests, and documentation to the current design instead of retaining old behavior.
- Document current installation, functionality, and usage. Do not add historical
  compatibility explanations, version-specific upgrade guides, or data conversion
  procedures unless explicitly requested.
- Implement backward compatibility or data conversion only when the user
  explicitly requests it. This policy remains in effect until the user removes
  it, including when compatibility becomes necessary for a stable release; do not
  infer that requirement from version numbers or release status alone.

# Documentation and environment maintenance

- When creating or updating `AGENTS.md`, never include secrets, credentials,
  sensitive internal information, or personal data. Use placeholders when
  examples are needed.

- Keep project UI and code messages in English by default.

- Use Title Case for static UI headings, labels, and buttons; sentence case for
  descriptions and help text. Preserve technical identifiers and user data.
  Set casing in strings, not CSS; keep tests and EN/KO documentation consistent.

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

# Commit message accuracy

- Draft commit messages from conversation context and fresh `git status --short`.
  Check unstaged/staged summaries (`git diff --stat`, `git diff --cached --stat`),
  then read only the file diffs needed to verify scope and substance. Avoid dumping
  full diffs, generated files, or lockfiles; inspect untracked/binary files as needed.
- Describe only verified changes in the requested scope; check recent commits when
  needed to exclude already committed work.
- A request for a commit message does not authorize staging or committing files.

# UI consistency and space efficiency

- Within an editor, use shared section headers, borders, backgrounds, and spacing
  for related settings; review the whole form for visual consistency.

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
