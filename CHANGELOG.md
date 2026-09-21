# CHANGELOG

## v2.3.0
- new:
    - custom themes: pick from 5 color palettes (UniDocs Blue, Nord, Dracula, Solarized, Monochrome) and switch between System / Light / Dark directly in the settings menu, applied live and remembered between restarts
    - every part of the UI now derives its colors from the active color scheme instead of hardcoded values, so light mode is properly readable everywhere (context menus, dialogs, tiles, tag chips)
- fix:
    - tag chips and filter chips now pick a readable text color based on the tag's own color instead of always assuming white text

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