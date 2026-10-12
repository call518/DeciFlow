# Documentation and environment maintenance

- When creating or updating `AGENTS.md`, never include secrets, credentials,
  sensitive internal information, or personal data. Use placeholders when
  examples are needed.

- Keep project UI and code messages in English by default.

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
