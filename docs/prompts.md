# Prompt Versioning

Prompts are registered in `app/prompts/registry.py`.

Each prompt records:

- Unique identifier
- Version
- Description and owner
- Status (`draft` / `approved` / `deprecated`)
- System and developer instructions
- Compatible model IDs
- SHA-256 content hash

Current approved prompt: `orion.chat.default` version `1.0.0`.

Security policies are not constructed from retrieved document content. System and developer instructions remain separate from user input and retrieved context.
