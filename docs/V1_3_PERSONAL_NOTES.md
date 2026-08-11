# DrFocus 1.3 Personal iteration

- Strict mode is monotonic: new blocking rules can be added, while existing rules cannot be edited, disabled or deleted until strict mode ends.
- Web protection follows the same principle: new sites/keywords and stronger toggles are allowed; removal/weakening is blocked during strict mode.
- The Personal Accessibility shield no longer blocks all of Android Settings. It activates only when an uninstall/removal flow targeting DrFocus is detected.
- Block overlays show a rotating original Arabic motivational message.
- Optional best-effort restart protection intercepts normal software power/restart menus during strict mode. Hardware forced reboot cannot be guaranteed by a normal Android app. Device/Profile Owner mode also applies DISALLOW_SAFE_BOOT while the option is active.
