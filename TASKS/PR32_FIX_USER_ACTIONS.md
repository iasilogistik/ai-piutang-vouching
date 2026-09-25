# PR32 Fix User Action Buttons

Issue reported: clicking `Nonaktifkan` and `Delete` in `/ui/users` did not provide visible result.

Fix scope:
- make row action handling visible near the buttons;
- add top action status banner;
- disable action buttons while processing;
- use a POST delete alias for browser/proxy compatibility;
- keep the DELETE endpoint for API clients;
- show success/error near the action, not only in the log area.
