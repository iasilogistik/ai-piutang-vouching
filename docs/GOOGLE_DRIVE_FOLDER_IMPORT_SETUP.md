# Google Drive Folder Import Setup

## Purpose

This guide documents the production setup required for importing documents from a Google Drive folder link.

The application already supports:

- direct PDF/JPG/PNG share links;
- ZIP share links;
- local bulk ZIP upload;
- combined Billing + SPJ upload.

Folder import needs a Google Drive API key because Google Drive folder contents must be listed through the Drive API.

## Required Vercel environment variable

Set the following variable in the Vercel project:

```text
GOOGLE_DRIVE_API_KEY=<Google Drive API key>
```

Do not commit the API key to GitHub.

## Google Drive permission requirement

The folder should be shared as:

```text
Anyone with the link
```

Files inside the folder should also be accessible through the same sharing scope.

## Supported folder contents

The importer processes:

- `.pdf`
- `.jpg`
- `.jpeg`
- `.png`
- `.zip`

Unsupported files are skipped and returned in the import log.

## Import modes

The browser workbench supports:

- `AUTO`: classify by folder/file name markers such as `BILLING`, `SPJ`, `GABUNGAN`, `COMBINED`.
- `BILLING`: import all supported files as Billing.
- `SPJ`: import all supported files as SPJ.
- `COMBINED`: import each supported file once as Billing and once as SPJ.

## How to use after deployment

Open:

```text
/ui/drive-import
```

Enter a valid Bearer Token, paste the Google Drive folder link, select the mode, and click:

```text
Import Folder Link
```

## Operational fallback

If `GOOGLE_DRIVE_API_KEY` has not been configured yet, use this fallback:

```text
Put all files into one ZIP
Upload ZIP to Google Drive
Set permission to Anyone with the link
Paste ZIP share link into /ui/drive-import
Click Import File/ZIP Link
```

This fallback does not require `GOOGLE_DRIVE_API_KEY`.

## Control notes

- The API key must be stored only as a Vercel environment variable.
- The application never displays the key in the browser.
- Folder import is still protected by Bearer Token and role authorization.
- Files that cannot be classified in `AUTO` mode are skipped instead of being forced into an audit evidence category.
