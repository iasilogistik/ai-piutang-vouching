# Revert User Management Note

This branch restores the application to the state before the user management sprint.

Reverted scope:
- `/ui/users` browser UI
- `/admin/users` admin APIs
- `public.user_roles` migration added in PR #31
- inactive-user enforcement added with that migration
- User Management link added to login page

Kept scope:
- `/login`
- `/auth/login`
- `/auth/refresh`
- `/auth/me`
- Existing upload, ZIP, Google Drive, UAT, and control evidence pages
