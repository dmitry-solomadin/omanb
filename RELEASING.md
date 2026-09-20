# Release preparation

## Listing metadata

- Name: omanb
- ID: `io.github.dmitry-solomadin.omanb`
- Repository: `https://github.com/dmitry-solomadin/omanb`
- Category: Productivity
- Tags: bar, quickshell
- License: MIT

The current marketplace registry had no occurrence of `omanb` or the proposed ID when checked on 2026-09-18. Recheck before submission; this does not reserve the ID or prove availability among retired listings.

## Before publishing

- Run `omarchy plugin validate .` on the target Omarchy installation.
- Run `python3 -m unittest discover -s tests -v` with Lua installed to include shortcut lifecycle tests.
- Smoke-test the renamed plugin in the shell: bar placement, popup, keyboard selection, create/edit/delete using disposable notes, and removal.
- Check missing nb and empty notebook behavior on a disposable test profile.
- Review the included `preview.png` and `docs/screenshots/neovim.png` screenshots before release.
- Review the version and license attribution.
- Push the reviewed release to the public GitHub repository.
- Submit through the marketplace form only after the owner approves publication.

Local manifest validation was performed with Omarchy 4.0.4-1. It checks the manifest and entry-point paths, not live QML behavior or every Omarchy version. Automated tests cover the nb helper, shortcut lifecycle, and scoped Neovim close behavior using isolated fixtures. Development checks also exercised the real nb CLI, Hyprland registration/cleanup, and isolation between two real Neovim processes; a fresh-install smoke test remains part of release preparation.

## Marketplace submission

Use the current form and requirements:

- https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml
- https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md

New listings need automated validation, an exact-commit baseline scan, and explicit maintainer approval. For later releases, use the verification form's "Verify and publish a newer upstream commit" action with the full commit SHA.
