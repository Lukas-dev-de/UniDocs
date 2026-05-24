# Unidocs

Set location for your files in the settings. Default will be under Documents/UniDocs
changing the location will not migrate your files!

You can add tags to documents by rightclicking them and applying existing tags or create new ones

You can sort by tags by clicking on them in the filterbar that appears when you have >0 Tags

Be aware, first start might take longer than usual ... I don't know why yet

# Contributing:

## Stuff to implement:
#### low effort
- [x] add more icons for selection
- [ ] feature: change/edit module icon like title
- [ ] feature: select for multiple tags by ctl click on tag filters

#### medium effort 
- [x] feature: applying tags by drag n dropping them from the filter bar onto documents 
- [ ] feature: add documents to module per drag n drop
- [ ] feature: add colors to modules
- [ ] feature: renaming files directly in import/import menu 
- [ ] fix: get links in settings to work 
- [ ] feature: selecting multiple files (for example with ctl+click or middle click) to apply tags or delete multiple at once
- [ ] feature: reorganise modules order in sidebar by draging
- [ ] feature: grouping modules in sidebar

#### high effort
- [ ] implement custom themes 
- [ ] file syncing (for example via self-hosting, github or googledrive ...)



If you have suggestions feel free to list them here.

<br>

## Branch Naming Convention

To maintain a clean and organized workflow, this project follows a specific branching strategy. Each branch name should consist of a category, an optional ID, and a short description.

**Format:** `category/id-description`

### Categories
- `feature/`: New functionality or UI components.
- `fix/`: Bug fixes and error handling.
- `refactor/`: Code improvements without changing functionality.
- `style/`: UI styling, colors, and layout tweaks.
- `docs/`: Updates to documentation or comments.

### Examples
- `feature/01-sidebar-navigation`
- `fix/02-pdf-display-offset`
- `style/03-dark-mode-colors`

### Workflow
1. Create a new branch: `git checkout -b category/id-description`
2. Commit your changes: `git commit -m "Brief explanation"`
3. Create Pull Request once the feature is stable and tested.

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

### Web

```bash
flet build web -v
```

For more details on building Web app, refer to the [Web Packaging Guide](https://flet.dev/docs/publish/web/).

