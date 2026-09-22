# Unidocs

Set location for your files in the settings. Default will be under Documents/UniDocs
changing the location will not migrate your files!

You can add tags to documents by rightclicking them and applying existing tags or create new ones

You can sort by tags by clicking on them in the filterbar that appears when you have >0 Tags

You can change the look of the app in the settings: choose one of 5 color palettes and switch between System, Light and Dark mode. The choice is applied instantly and remembered.

Be aware, first start might take longer than usual ... I don't know why yet

# Contributing:

## Workflow

`main` always reflects the latest release. Changes for a new version are collected on a
`release/X.Y.Z` branch (for example `release/2.3.0`); once the version is ready it is
merged into `main` and tagged. Small fixes can go directly on `main`.

If a fix lands on `main` while a release branch is still open, merge `main` back into the
release branch so the two do not drift apart.

### Cutting a release

The version number is written down in three places (`pyproject.toml`, `CURRENT_VERSION` in
`src/ui/settings_dialog.py` and the newest `## vX.Y.Z` heading in `CHANGELOG.md`).
`tools/check_version.py` makes sure they agree, and the release build refuses to run if they
do not.

1. On `release/X.Y.Z`: set `CURRENT_VERSION` in `src/ui/settings_dialog.py` and add the
   `## vX.Y.Z` section to `CHANGELOG.md` while you work on it.
2. As the last commit on the branch, bump `version` in `pyproject.toml` to `X.Y.Z` and check
   all three places:

   ```bash
   python tools/check_version.py vX.Y.Z
   ```

3. Merge `release/X.Y.Z` into `main` (keep the commits, do not squash).
4. On GitHub: *Releases -> Draft a new release*, tag `vX.Y.Z` targeting `main`, write the
   notes and publish. Publishing starts the `Release build` workflow, which builds every
   platform and attaches the files to the release (see below).
5. Merge `main` back into the next release branch.

## Stuff to implement:
#### low effort
- [x] add more icons for selection
- [x] feature: change/edit module icon like title
- [ ] feature: select for multiple tags by ctl click on tag filters

#### medium effort 
- [x] feature: applying tags by drag n dropping them from the filter bar onto documents 
- [x] feature: renaming files directly in import/import menu 
- [ ] feature: add documents to module per drag n drop
- [x] feature: add colors to modules
- [x] fix: get links to repository in settings to work 
- [x] feature: selecting multiple files (for example with ctl+click or middle click) to apply tags or delete multiple at once
- [x] feature: reorganise modules order in sidebar from the right click menu (no drag n drop)
- [ ] feature: grouping modules in sidebar

#### high effort
- [x] feature: implement custom themes 
- [ ] feature: file syncing (for example via self-hosting, github or googledrive ...)



If you have suggestions feel free to list them here.

<br>

# For Developers

## Run the app

### uv

Run as a desktop app:

```bash
uv run flet run
```

Run as a web app:

```bash
uv run flet run --web
```

For more details on running the app, refer to the [Getting Started Guide](https://flet.dev/docs/).

## Build the app

The commands below are what CI runs for you when a release is published (see
[Releases](#releases-automated)); use them locally for one-off builds.

### Android

```bash
flet build apk -v
```

For more details on building and signing `.apk` or `.aab`, refer to the [Android Packaging Guide](https://flet.dev/docs/publish/android/).

### iOS

```bash
flet build ipa -v
```

For more details on building and signing `.ipa`, refer to the [iOS Packaging Guide](https://flet.dev/docs/publish/ios/).

### macOS

```bash
flet build macos -v
```

For more details on building macOS package, refer to the [macOS Packaging Guide](https://flet.dev/docs/publish/macos/).

### Linux

```bash
flet build linux -v
```

For more details on building Linux package, refer to the [Linux Packaging Guide](https://flet.dev/docs/publish/linux/).

### Windows

```bash
flet build windows -v
```

For more details on building Windows package, refer to the [Windows Packaging Guide](https://flet.dev/docs/publish/windows/).

This only produces the portable folder `build/windows/`. The release workflow wraps that folder
into a real installer with [Inno Setup](https://jrsoftware.org/isinfo.php) (`installer/unidocs.iss`),
which adds a Start Menu entry, a desktop shortcut and an uninstaller in *Apps & features*.
To test it locally after the build above:

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/unidocs.iss
```

### Web

```bash
flet build web -v
```

For more details on building Web app, refer to the [Web Packaging Guide](https://flet.dev/docs/publish/web/).

## Releases (automated)

Publishing a release on GitHub triggers `.github/workflows/release-build.yml`, which builds
and attaches these files to that release:

| File | Platform |
| --- | --- |
| `UniDocs-linux-x86_64.zip` | Linux, extract and run `./unidocs` |
| `UniDocs-windows-x86_64.zip` | Windows, portable: extract and run `unidocs.exe` |
| `UniDocs-<version>-windows-x86_64-setup.exe` | Windows installer, see below |
| `UniDocs-macos-universal.zip` | macOS, extract, drag `unidocs.app` to Applications |
| `UniDocs-web.zip` | static web build, needs to be served by a web server |

Notes:

- The workflow only runs on `release` events once it exists on `main`, so merge it into
  `main` before publishing the first automated release.
- `flet build` and the Flutter SDK version are pinned in the `env:` block of the workflow;
  bump them together with `flet` in `pyproject.toml`.
- The Windows installer (`installer/unidocs.iss`) installs per user by default, so it needs no
  admin rights and lands in `%LOCALAPPDATA%\Programs\UniDocs`; an admin gets a dialog to install
  for all users instead. It shows a desktop shortcut task (checked by default) and registers an
  uninstaller in *Apps & features*. Upgrades replace the previous install (fixed `AppId`).
- Nothing is code signed. Windows shows a SmartScreen warning ("More info" -> "Run anyway")
  for both the portable zip and the installer, and macOS blocks the app until it is allowed in
  *System Settings -> Privacy & Security -> Open Anyway*. Flet 0.84 has no support for signing
  or notarizing macOS bundles yet.
- The workflow can also be started by hand from the Actions tab to test a build without
  creating a release.
- A signed `.ipa` for iPad/iPhone needs an Apple Developer Program membership; that build
  lives in `.github/workflows/ios.yml` and is manual-only.

Optional extras when a build needs them: `--compile-app --compile-packages` (ship `.pyc`,
starts faster but keeps no source around) and `--arch` for other CPU architectures.
