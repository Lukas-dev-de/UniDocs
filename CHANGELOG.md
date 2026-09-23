# CHANGELOG

## Unreleased
- new:
    - settings menu: "Check for updates" button. It asks the GitHub releases of this repo for the newest version and says whether you are up to date or a newer one is out
    - UniDocs looks for a new release once per start, quietly in the background. Patch releases (2.3.0 -> 2.3.1) install themselves and the app restarts into the new version
    - bigger updates (new features, 2.4.0) show up once as a popup: "Install now" or "Later". The same version never pops up a second time - installing it later is always possible from the settings
    - settings: switch "Install patches automatically" to turn the silent patch install off
    - Linux: releases ship an `install.sh` and a `.tar.gz` instead of a plain zip. `install.sh` sets UniDocs up for the current user only (no root): app in `~/.local/share/unidocs`, `unidocs` on the `PATH`, icon and menu entry, `--uninstall` takes it away again
    - Linux: releases also ship a single-file `.AppImage` (chmod +x and run)
    - Linux finally updates itself too: both the `install.sh` build and the AppImage install patch releases on startup and have an "Install now" button, just like the Windows setup. The old zip could not
- change:
    - the Windows installer also starts UniDocs again after a silent install, which is what the in-app updater relies on
    - config.json: several instances of the settings can no longer write over each other's keys
    - on macOS the update buttons still hand the archive over to the browser: a portable `.app` zip cannot replace itself

## v2.3.0
- new:
    - Windows releases now also ship a real installer next to the portable zip: it adds a Start Menu entry, an (optional) desktop shortcut and an uninstaller in "Apps & features", and needs no admin rights
    - modules can be given an accent color, shown on their tile in the sidebar; modules without one keep following the theme as before
    - modules can be edited from the sidebar context menu (right click): title, description, icon and color in one dialog
    - modules can be moved up and down from the sidebar context menu (right click); the arrangement is remembered in a .order file next to tags.json
    - custom themes: pick from 5 color palettes (UniDocs Blue, Nord, Dracula, Solarized, Monochrome) and switch between System / Light / Dark directly in the settings menu, applied live and remembered between restarts
    - every part of the UI now derives its colors from the active color scheme instead of hardcoded values, so light mode is properly readable everywhere (context menus, dialogs, tiles, tag chips)
- fix:
    - settings menu: the color palette dropdown no longer sits flush against the System / Light / Dark switch
    - settings menu: the dialog body now scrolls instead of spilling past the dialog when the window is made very small
    - renaming a module to the name of another module is now rejected with an error instead of overwriting that module's folder
    - tag chips and filter chips now pick a readable text color based on the tag's own color instead of always assuming white text
    - renaming a module no longer makes it jump to the end of the sidebar

## v2.2.0
- feature:
    - rename files directly in import menu
    - select multiple documents at once (Ctrl/Cmd-click, Shift-range or long-press) to apply tags, open or delete them in batch
- fix:
    - in the import menu when selecting files and then selecting more files it would forget the firstly selected ones. This is now no longer the case. Instead they now just get added to the list
    - selection checkmark in the tile view no longer shrinks the document tiles

## v2.1.1
- fix:
    - dragging tags onto documents now also works in list view
    - settings menu now shows the correct version 

## v2.1.0
- new:
    - tags can be added by dragging from the filter bar onto documents

## v2.0.2
- change:
    - moved settings icon from top left to bottom left
    - added Themes coming soon to settings menu
    - removed long text from settings

## v2.0.0
- new:  
    - you can now add tags to documents
- fix:
    - rightclick context menues now dissappear when clicking somewhere else
    - fixed bug where renaming documents would break integrity

## v1.0.1
- Bug fixes 
- fixing AI-Slop from initial UI-Structure

## v1.0.0
Initial Release