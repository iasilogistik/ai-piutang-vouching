# Vercel Environment Setup

## Google Drive folder import

To enable direct Google Drive folder import, configure this environment variable in the Vercel project:

```text
GOOGLE_DRIVE_API_KEY=<Google Drive API key>
```

Recommended scope:

- Production: required for live folder import.
- Preview: optional for testing pull requests.
- Development: optional for local tests.

## Verification checklist

After setting the environment variable and redeploying production:

1. Open `/health` and confirm it returns healthy.
2. Open `/ui/drive-import`.
3. Enter a valid Bearer Token.
4. Paste a Google Drive folder link shared as `Anyone with the link`.
5. Click `Import Folder Link`.
6. Confirm the import result shows `SUCCESS`, `SKIPPED`, or `ERROR` per file.
7. Open `/ui/control-evidence` and confirm SPJ evidence is visible.

## Fallback if key is not ready

Use ZIP-based share link import:

1. Put all documents into a ZIP file.
2. Upload the ZIP to Google Drive.
3. Share it as `Anyone with the link`.
4. Paste the ZIP share link into `/ui/drive-import`.
5. Click `Import File/ZIP Link`.

This path does not need the Google Drive API key.
