# Drive Secret Manager moved

This tool is maintained as a separate project and is no longer bundled with `paper-live`.

- **Repository:** https://github.com/raonwglobal/drive-secret-manager
- **Setup and security instructions:** see the standalone repository README.
- **Integration:** both projects can use the same encrypted Google Drive vault when configured with the same `GOOGLE_DRIVE_SECRET_FILE_ID`, `GOOGLE_DRIVE_ACCESS_TOKEN`, and `GOOGLE_DRIVE_SECRET_KEY`. Keep the OAuth token and encryption key outside Google Drive and source control.

Do not copy secrets into this repository.
