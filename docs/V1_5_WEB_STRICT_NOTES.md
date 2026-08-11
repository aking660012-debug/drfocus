# DrFocus 1.5 Personal — Web & Strict overhaul

This iteration fixes Personal-release website/keyword blocking, strengthens supported-browser URL/text inspection, optionally blocks unsupported browsers, and aligns Strict Mode activation with the observed four-step flow: restriction editing scope, extra anti-bypass restrictions, deactivation method, and Device Admin/system protection review.

Owner mode uses Android DevicePolicyManager user restrictions for app-data, uninstall and install controls. Ordinary personally owned devices use the narrower Personal Accessibility shield as best-effort fallback. The browser/content filter remains local and does not perform TLS interception.
