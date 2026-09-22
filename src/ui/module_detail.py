import flet as ft
from models.module import Module
from models.document import Document
from app_storage.module_store import ModuleStore
from ui.import_dialog import ImportDialog
from ui.context_menu import ContextMenu
from ui.tag_manager import TagManager
from ui.components.tag_dialog import TagDialog
from ui.components.tag_colors import TAG_PALETTE
from ui.theme import on_color
from ui.components.dialogs import ConfirmDialog, RenameDialog
from pathlib import Path
import subprocess
import sys


@ft.control
class ModuleDetail(ft.Container):

    def __init__(self, store: ModuleStore):
        super().__init__()

        self._store = store
        self.module: Module | None = None
        self._list_view = False
        self._sort_asc = True
        self._active_tag_filter: str | None = None  # currently selected tag filter
        self._tag_manager: TagManager | None = None

        #  Selection state 
        self._selected: set[str] = set()          # filepaths of selected documents
        self._select_mode: bool = False           # explicit "select" toggle
        self._anchor_path: str | None = None      # anchor for shift-range selection
        self._visible_paths: list[str] = []       # display order of current docs
        # modifier keys, tracked via page.on_keyboard_event
        self._mod_ctrl: bool = False
        self._mod_shift: bool = False
        self._mod_meta: bool = False

        #  Title: text display + inline editor 
        self.title_text = ft.Text(
            value="No Module Selected",
            size=32,
            weight=ft.FontWeight.BOLD,
        )
        self.title_field = ft.TextField(
            text_size=32,
            border=ft.InputBorder.UNDERLINE,
            expand=True,
            visible=False,
            on_submit=self._commit_title,
            on_blur=self._commit_title,
        )
        self._title_click = ft.GestureDetector(
            content=self.title_text,
            on_tap= self._start_title_edit,
            mouse_cursor=ft.MouseCursor.TEXT,
        )

        #  Description: text display + inline editor 
        self.description_text = ft.Text(
            value="Select a module to display information. You can create a new module by ",
            size=16,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self.description_field = ft.TextField(
            text_size=16,
            border=ft.InputBorder.UNDERLINE,
            hint_text="Add a description…",
            expand=True,
            visible=False,
            on_submit=self._commit_description,
            on_blur=self._commit_description,
        )
        self._desc_click = ft.GestureDetector(
            content=self.description_text,
            on_tap=self._start_desc_edit,
            mouse_cursor=ft.MouseCursor.TEXT,
        )

        #  Toolbar buttons 
        self._sort_toggle = ft.IconButton(
            icon=ft.Icons.SORT_BY_ALPHA,
            tooltip="Sort Z → A",
            on_click=self._toggle_sort,
        )
        self._view_toggle = ft.IconButton(
            icon=ft.Icons.VIEW_LIST,
            tooltip="Switch to list view",
            on_click=self._toggle_view,
        )
        self._import_btn = ft.FloatingActionButton(
            icon=ft.Icons.UPLOAD_FILE,
            tooltip="Import documents",
            on_click=self._open_import,
            bgcolor=ft.Colors.PRIMARY,
            mini=True,
        )
        self._select_btn = ft.IconButton(
            icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
            tooltip="Select documents",
            on_click=self._toggle_select_mode,
        )

        #  Tag filter bar 
        self._tag_filter_row = ft.Row(
            wrap=True,
            spacing=6,
            run_spacing=6,
            visible=False,
        )

        #  Import dialog 
        self._import_dialog = ImportDialog(
            store=self._store,
            on_import=self._on_import_done,
        )

        #  Document views 
        self.documents_grid = ft.GridView(
            expand=True,
            runs_count=5,
            max_extent=160,
            spacing=8,
            run_spacing=8,
        )
        self.documents_list = ft.ListView(
            expand=True,
            spacing=4,
            visible=False,
        )

        #  Selection action bar (visible while selecting) 
        self._sel_count_text = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
        self._sel_open_btn = ft.TextButton(
            "Open", icon=ft.Icons.OPEN_IN_NEW, on_click=self._batch_open,
        )
        self._sel_tag_btn = ft.TextButton(
            "Tags", icon=ft.Icons.LABEL_OUTLINE, on_click=self._batch_tag,
        )
        self._sel_delete_btn = ft.TextButton(
            "Delete", icon=ft.Icons.DELETE_OUTLINE, on_click=self._batch_delete,
            style=ft.ButtonStyle(color=ft.Colors.ERROR),
        )
        self._sel_done_btn = ft.TextButton(
            "Done", icon=ft.Icons.CLOSE, on_click=self._exit_select_mode,
        )
        self._selection_bar = ft.Container(
            visible=False,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=10,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            content=ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=18, color=ft.Colors.PRIMARY),
                    self._sel_count_text,
                    ft.Container(expand=True),
                    self._sel_open_btn,
                    self._sel_tag_btn,
                    self._sel_delete_btn,
                    self._sel_done_btn,
                ],
            ),
        )

        #  Styling 
        self.border_radius = 16
        self.padding = 16
        self.expand = 19
        self.bgcolor = ft.Colors.SURFACE

        #  Layout 
        self.content = ft.Column(
            spacing=10,
            expand=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Column(
                            spacing=4,
                            expand=True,
                            controls=[
                                # Title row: static text XOR text field
                                ft.Row(controls=[self._title_click, self.title_field]),
                                # Description row: static text XOR text field
                                ft.Row(controls=[self._desc_click, self.description_field]),
                            ],
                        ),
                        ft.Row(
                            spacing=4,
                            controls=[self._select_btn, self._sort_toggle, self._view_toggle, self._import_btn],
                        ),
                    ],
                ),
                ft.Divider(color=ft.Colors.OUTLINE_VARIANT),
                self._tag_filter_row,
                self._selection_bar,
                self.documents_grid,
                self.documents_list,
            ],
        )

    #  lifecycle 

    def show_error(self, message: str):
        self.page.show_snack_bar(ft.SnackBar(content=ft.Text(message)))

    def did_mount(self):
        self._import_dialog.attach_to_page(self.page)

        self._ctx_menu = ContextMenu()
        self.page.overlay.append(self._ctx_menu)

        self._tag_manager = TagManager(
            page=self.page,
            store=self._store,
            on_changed=self._reload_current_module,
        )

        # modifier keys aren't reported on tap events, so track them globally
        try:
            self.page.on_keyboard_event = self._on_key_event
        except Exception as ex:
            print(f"Keyboard events unavailable: {ex}")

        self.page.update()

    def will_unmount(self):
        page = self.page
        if page is None:
            return

        if self._tag_manager:
            self._tag_manager.cleanup()

        for item in [
            self._import_dialog,
            self._import_dialog._file_picker,
            self._ctx_menu,
        ]:
            if item in page.overlay:
                page.overlay.remove(item)

        try:
            page.on_keyboard_event = None
        except Exception:
            pass

    #  public 

    def set_module(self, module: Module):
        # Always re-read from disk so tag colours/names changed while viewing
        # another module are reflected immediately on switch.
        fresh = None
        for m in self._store.load_all():
            if m.title == module.title:
                fresh = m
                break
        self.module = fresh if fresh is not None else module
        self._active_tag_filter = None
        self._select_mode = False
        self._selected.clear()
        self._anchor_path = None
        self._show_title_text(self.module.title)
        self._show_desc_text(self.module.description)
        self._refresh_documents()
        self.update()

    #  inline TITLE editing 

    async def _start_title_edit(self, e):
        if self.module is None:
            return
        self.title_field.value = self.module.title
        self._title_click.visible = False
        self.title_field.visible = True
        self.update()
        await self.title_field.focus()

    def _commit_title(self, e):
        new_title = (self.title_field.value or "").strip()
        if not new_title or self.module is None:
            self._show_title_text(self.module.title if self.module else "")
            self.update()
            return
        if new_title != self.module.title:
            if self._store.rename_conflict(self.module, new_title):
                # Refuse rather than clobber the other module's folder.
                self._show_title_text(self.module.title)
                self.update()
                self.show_error(f'Another module is already called "{new_title}".')
                return
            try:
                self._store.rename_module(self.module, new_title)
            except Exception as ex:
                print(f"Rename failed: {ex}")
        self._show_title_text(self.module.title)
        self.update()

    def _show_title_text(self, value: str):
        self.title_text.value = value
        self._title_click.visible = True
        self.title_field.visible = False

    #  inline DESCRIPTION editing 

    async def _start_desc_edit(self, e):
        if self.module is None:
            return
        self.description_field.value = self.module.description
        self._desc_click.visible = False
        self.description_field.visible = True
        self.update()
        await self.description_field.focus()

    def _commit_description(self, e):
        new_desc = (self.description_field.value or "").strip()
        if self.module is None:
            self._show_desc_text("")
            self.update()
            return
        self.module.description = new_desc
        try:
            self._store.save_module(self.module)
        except Exception as ex:
            print(f"Save description failed: {ex}")
        self._show_desc_text(new_desc)
        self.update()

    def _show_desc_text(self, value: str):
        self.description_text.value = value or "Click to add a description…"
        self.description_text.color = ft.Colors.ON_SURFACE_VARIANT if value else ft.Colors.OUTLINE
        self._desc_click.visible = True
        self.description_field.visible = False

    #  toolbar 

    def _toggle_sort(self, e):
        self._sort_asc = not self._sort_asc
        self._sort_toggle.tooltip = "Sort Z → A" if self._sort_asc else "Sort A → Z"
        self._refresh_documents()
        self.update()

    def _toggle_view(self, e):
        self._list_view = not self._list_view
        if self._list_view:
            self._view_toggle.icon = ft.Icons.GRID_VIEW
            self._view_toggle.tooltip = "Switch to grid view"
        else:
            self._view_toggle.icon = ft.Icons.VIEW_LIST
            self._view_toggle.tooltip = "Switch to list view"
        self._refresh_documents()
        self.update()

    def _open_import(self, e):
        self._import_dialog.refresh_modules()
        if self.module:
            self._import_dialog.open_for_module(self.module)
        else:
            self._import_dialog.open = True
            self._import_dialog.update()

    #  import callback 

    def _on_import_done(self, module: Module, docs):
        if self.module and module.title == self.module.title:
            self._reload_current_module()

    def _reload_current_module(self):
        if self.module is None:
            return
        # Always re-read from disk so tag color/name changes made while viewing
        # another module are picked up correctly.
        refreshed = None
        for m in self._store.load_all():
            if m.title == self.module.title:
                refreshed = m
                break
        if refreshed is not None:
            self.module = refreshed
        self._refresh_documents()
        self.update()

    def _get_filtered_and_sorted_docs(self) -> list:
        if self.module is None:
            return []

        docs = self.module.documents
        if self._active_tag_filter:
            docs = [
                d for d in docs
                if any(t.id == self._active_tag_filter for t in d.tags)
            ]
        return sorted(docs, key=lambda d: d.title.lower(), reverse=not self._sort_asc)

    def _render_grid(self, docs):
        self.documents_grid.controls.clear()
        for doc in docs:
            self.documents_grid.controls.append(self._doc_tile(doc))

    def _render_list(self, docs):
        self.documents_list.controls.clear()
        for doc in docs:
            self.documents_list.controls.append(self._doc_row(doc))

    #  document rendering

    def _refresh_documents(self):
        if self.module is None:
            self._tag_filter_row.visible = False
            self._selection_bar.visible = False
            self.documents_grid.controls.clear()
            self.documents_list.controls.clear()
            return

        # --- rebuild tag filter bar ---
        all_tags = self._store.load_all_tags()
        self._tag_filter_row.controls.clear()
        if all_tags:
            self._tag_filter_row.visible = True
            all_selected = self._active_tag_filter is None
            self._tag_filter_row.controls.append(
                self._filter_chip("All", None, all_selected)
            )
            for tag in sorted(all_tags, key=lambda t: t["name"]):
                selected = self._active_tag_filter == tag["id"]
                self._tag_filter_row.controls.append(
                    self._filter_chip(tag["name"], tag["id"], selected, tag["color"])
                )
        else:
            self._tag_filter_row.visible = False

        # --- get data and render ---
        docs = self._get_filtered_and_sorted_docs()
        self._visible_paths = [d.filepath for d in docs]

        # Keep selection consistent with what is currently visible (e.g. when
        # a tag filter hides docs, they should no longer stay selected).
        if self._selected:
            self._selected &= set(self._visible_paths)
            if self._anchor_path not in self._selected:
                self._anchor_path = None

        if self._list_view:
            self.documents_grid.visible = False
            self.documents_list.visible = True
            self._render_list(docs)
        else:
            self.documents_grid.visible = True
            self.documents_list.visible = False
            self._render_grid(docs)

        self._update_selection_bar()

    def _filter_chip(self, label: str, tag_id, selected: bool, color: str = "#1565C0") -> ft.Control:
        chip_content = ft.Container(
            bgcolor=color if selected else ft.Colors.SURFACE_CONTAINER_HIGH,
            border_radius=16,
            border=ft.Border.all(2, color) if not selected else None,
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            on_click=lambda e, t=tag_id: self._set_tag_filter(t),
            ink=True,
            content=ft.Text(
                label,
                size=12,
                color=on_color(color) if selected else ft.Colors.ON_SURFACE_VARIANT,
            ),
        )
        # "All" chip has no tag_id - no right-click menu
        if tag_id is None:
            return chip_content
        return ft.GestureDetector(
            content=ft.Draggable(data=tag_id, content=chip_content),
            on_secondary_tap_down=lambda e, tid=tag_id: self._show_tag_menu(e, tid),
        )

    def _set_tag_filter(self, tag_name):
        self._active_tag_filter = tag_name
        self._refresh_documents()
        self.update()

    #  selection 

    def _is_selecting(self) -> bool:
        return self._select_mode or bool(self._selected)

    def _toggle_select_mode(self, e=None):
        if self._is_selecting():
            self._select_mode = False
            self._selected.clear()
            self._anchor_path = None
        else:
            self._select_mode = True
        self._refresh_documents()
        self.update()

    def _exit_select_mode(self, e=None):
        self._select_mode = False
        self._selected.clear()
        self._anchor_path = None
        self._refresh_documents()
        self.update()

    def _select_doc(self, doc: Document, range_: bool = False):
        path = doc.filepath
        anchor_valid = (
            range_
            and self._anchor_path in self._visible_paths
            and path in self._visible_paths
        )
        if anchor_valid:
            a = self._visible_paths.index(self._anchor_path)
            b = self._visible_paths.index(path)
            lo, hi = sorted((a, b))
            self._selected = set(self._visible_paths[lo:hi + 1])
        else:
            if path in self._selected:
                self._selected.discard(path)
                if self._anchor_path == path:
                    self._anchor_path = None
            else:
                self._selected.add(path)
                self._anchor_path = path
        self._refresh_documents()
        self.update()

    def _on_doc_click(self, e, doc: Document):
        # Ctrl/Cmd/Shift or an active selection => select instead of opening.
        if self._is_selecting() or self._mod_ctrl or self._mod_meta or self._mod_shift:
            self._select_doc(doc, range_=self._mod_shift)
        else:
            self._open_file(doc.filepath)

    def _on_doc_long_press(self, e, doc: Document):
        # Touch friendly: long press starts a selection including this doc.
        if doc.filepath not in self._selected:
            self._selected.add(doc.filepath)
        self._anchor_path = doc.filepath
        self._select_mode = True
        self._refresh_documents()
        self.update()

    def _on_key_event(self, e):
        self._mod_ctrl = bool(getattr(e, "ctrl", False))
        self._mod_shift = bool(getattr(e, "shift", False))
        self._mod_meta = bool(getattr(e, "meta", False))
        key = getattr(e, "key", "") or ""
        if key in ("Escape", "Esc") and self._is_selecting():
            self._exit_select_mode()

    def _selected_docs(self) -> list[Document]:
        if self.module is None:
            return []
        return [d for d in self.module.documents if d.filepath in self._selected]

    def _update_selection_bar(self):
        active = self._is_selecting()
        count = len(self._selected)
        self._selection_bar.visible = active
        self._sel_count_text.value = f"{count} selected" if count else "Selection mode"
        has_docs = count > 0
        self._sel_open_btn.disabled = not has_docs
        self._sel_tag_btn.disabled = not has_docs
        self._sel_delete_btn.disabled = not has_docs
        self._select_btn.icon = ft.Icons.CLOSE if active else ft.Icons.CHECK_CIRCLE_OUTLINE
        self._select_btn.tooltip = "Exit selection" if active else "Select documents"
        self._select_btn.icon_color = ft.Colors.PRIMARY if active else None

    def _sel_badge(self) -> ft.Control:
        return ft.Container(
            width=22,
            height=22,
            border_radius=11,
            bgcolor=ft.Colors.PRIMARY,
            border=ft.Border.all(2, ft.Colors.SURFACE),
            content=ft.Icon(ft.Icons.CHECK, size=14, color=ft.Colors.ON_PRIMARY),
        )

    def _tag_chip(self, tag, size: int) -> ft.Control:
        """Pill for a tag; text colour derived from the (user-chosen) colour."""
        color = getattr(tag, "color", None) or "#1565C0"
        name = getattr(tag, "name", tag)
        return ft.Container(
            bgcolor=color,
            border_radius=10,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
            content=ft.Text(name, size=size, color=on_color(color)),
        )

    #  batch actions 

    def _batch_open(self, e):
        for doc in self._selected_docs():
            self._open_file(doc.filepath)

    def _batch_tag(self, e):
        docs = self._selected_docs()
        if not docs:
            return
        self._tag_manager.tag_dialog.open_for_documents(docs, self.module)

    def _batch_delete(self, e):
        docs = self._selected_docs()
        if not docs:
            return

        def on_confirm():
            try:
                for doc in list(docs):
                    self._store.delete_document(self.module, doc)
            except Exception as ex:
                self.show_error(f"Delete failed: {ex}")
            self._select_mode = False
            self._selected.clear()
            self._anchor_path = None
            self._reload_current_module()

        dlg = ConfirmDialog(
            "Delete documents",
            f"Delete {len(docs)} documents? This cannot be undone.",
            on_confirm,
        )
        self.page.overlay.append(dlg)
        self.page.update()
        dlg.open = True
        dlg.update()

    #  tag filter context menu 

    def _show_tag_menu(self, e: ft.TapEvent, tag_id: str):
        self._tag_manager.show_menu(e, tag_id)
    def _tag_change_color(self, tag_id: str):
        self._tag_manager._start_change_color(tag_id)
    def _commit_tag_color(self, hex_color: str):
        self._tag_manager._commit_tag_color(hex_color)
    def _tag_rename(self, tag_id: str, current_name: str):
        self._tag_manager._start_rename(tag_id, current_name)
    def _commit_tag_rename(self, e):
        self._tag_manager._commit_tag_rename(e)
    def _tag_delete(self, tag_id: str, tag_name: str):
        self._tag_manager._start_delete(tag_id, tag_name)
    def _apply_tag_delete(self, tag_id: str):
        self._tag_manager.store.remove_global_tag(tag_id)
        if self._active_tag_filter == tag_id:
            self._active_tag_filter = None
        self._reload_current_module()


    def _ext_icon(self, suffix: str) -> str:
        suffix = suffix.lower()
        mapping = {
            ".pdf":  ft.Icons.PICTURE_AS_PDF,
            ".doc":  ft.Icons.DESCRIPTION,
            ".docx": ft.Icons.DESCRIPTION,
            ".ppt":  ft.Icons.SLIDESHOW,
            ".pptx": ft.Icons.SLIDESHOW,
            ".xls":  ft.Icons.TABLE_CHART,
            ".xlsx": ft.Icons.TABLE_CHART,
            ".png":  ft.Icons.IMAGE,
            ".jpg":  ft.Icons.IMAGE,
            ".jpeg": ft.Icons.IMAGE,
            ".gif":  ft.Icons.IMAGE,
            ".mp4":  ft.Icons.VIDEO_FILE,
            ".mp3":  ft.Icons.AUDIO_FILE,
            ".zip":  ft.Icons.FOLDER_ZIP,
            ".py":   ft.Icons.CODE,
            ".txt":  ft.Icons.ARTICLE,
            ".md":   ft.Icons.ARTICLE,
        }
        return mapping.get(suffix, ft.Icons.INSERT_DRIVE_FILE)

    def _doc_tile(self, doc:Document):
        suffix = Path(doc.filepath).suffix
        tag_chips = ft.Row(
            wrap=True,
            spacing=4,
            run_spacing=4,
            controls=[self._tag_chip(t, 9) for t in doc.tags],
        )
        selected = doc.filepath in self._selected
        inner = ft.Container(
            border_radius=10,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST if selected else ft.Colors.SURFACE_CONTAINER_HIGH,
            border=ft.Border.all(2, ft.Colors.PRIMARY) if selected else None,
            padding=10,
            ink=True,
            on_click=lambda e, d=doc: self._on_doc_click(e, d),
            tooltip="Open · Ctrl+Click to select · Right-click for options",
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
                controls=[
                    ft.Icon(self._ext_icon(suffix), size=40, color=ft.Colors.PRIMARY),
                    ft.Text(
                        doc.title,
                        size=12,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        suffix.lstrip(".").upper(),
                        size=10,
                        color=ft.Colors.OUTLINE,
                    ),
                    tag_chips,
                ],
            ),
        )
        tile: ft.Control = (
            ft.Stack(
                fit=ft.StackFit.EXPAND,
                controls=[
                    inner,
                    ft.Container(
                        content=self._sel_badge(),
                        right=6,
                        top=6,
                        width=22,
                        height=22,
                    ),
                ]
            )
            if selected
            else inner
        )
        return ft.GestureDetector(
            content=ft.DragTarget(
                content=tile,
                on_will_accept=lambda e : True,
                on_accept=lambda e : self._on_doc_accept_tag(e, doc=doc)
            ),
            on_secondary_tap_down=lambda e, d=doc: self._show_doc_menu(e, d),
            on_long_press=lambda e, d=doc: self._on_doc_long_press(e, d),
        )

    def _doc_row(self, doc):
        suffix = Path(doc.filepath).suffix
        tag_chips = ft.Row(
            spacing=4,
            controls=[self._tag_chip(t, 10) for t in doc.tags],
        )
        selected = doc.filepath in self._selected
        inner = ft.Container(
            border_radius=8,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST if selected else ft.Colors.SURFACE_CONTAINER_HIGH,
            border=ft.Border.all(2, ft.Colors.PRIMARY) if selected else None,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            ink=True,
            on_click=lambda e, d=doc: self._on_doc_click(e, d),
            tooltip="Open · Ctrl+Click to select · Right-click for options",
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(self._ext_icon(suffix), size=24, color=ft.Colors.PRIMARY),
                    ft.Text(
                        doc.title,
                        size=14,
                        expand=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    tag_chips,
                    ft.Text(
                        suffix.lstrip(".").upper(),
                        size=11,
                        color=ft.Colors.OUTLINE,
                        width=40,
                        text_align=ft.TextAlign.RIGHT,
                    ),
                ],
            ),
        )
        tile: ft.Control = (
            ft.Stack(
                controls=[
                    inner,
                    ft.Container(
                        content=self._sel_badge(),
                        alignment=ft.Alignment.CENTER_LEFT,
                        margin=ft.margin.only(left=12),
                    ),
                ]
            )
            if selected
            else inner
        )
        return ft.GestureDetector(
            content=ft.DragTarget(
                content=tile,
                on_will_accept=lambda e : True,
                on_accept=lambda e : self._on_doc_accept_tag(e, doc=doc)
            ),
            on_secondary_tap_down=lambda e, d=doc: self._show_doc_menu(e, d),
            on_long_press=lambda e, d=doc: self._on_doc_long_press(e, d),
        )


    def _on_doc_accept_tag(self, e: ft.DragTargetEvent, doc : Document):
        tag_id: str = e.src.data

        # No-op if already assigned
        if any(t.id == tag_id for t in doc.tags):
            return

        tag_dict = self._store.get_tag_by_id(tag_id)
        if tag_dict is None:
            return  # tag was deleted between drag start and drop

        # Persist: merge new ID with existing ones
        current_ids = [t.id for t in doc.tags]
        self._store.save_doc_tags(self.module, doc, current_ids + [tag_id])

        # Update in-memory so the tile reflects the change immediately
        from models.tag import Tag
        doc.tags.append(Tag(tag_dict["id"], tag_dict["name"], tag_dict["color"]))

        self._refresh_documents()
        self.update()

    #  document context menu 

    def _show_doc_menu(self, e: ft.TapEvent, doc):
        self._ctx_menu.show(
            e.global_position.x,
            e.global_position.y,
            [
                ("Open", ft.Icons.OPEN_IN_NEW, ft.Colors.ON_SURFACE,
                 lambda d=doc: self._open_file(d.filepath)),
                ("Select", ft.Icons.CHECK_CIRCLE_OUTLINE, ft.Colors.ON_SURFACE,
                 lambda d=doc: self._select_doc(d)),
                ("Manage Tags", ft.Icons.LABEL_OUTLINE, ft.Colors.PRIMARY,
                 lambda d=doc: self._doc_manage_tags(d)),
                ("Rename", ft.Icons.DRIVE_FILE_RENAME_OUTLINE, ft.Colors.ON_SURFACE,
                 lambda d=doc: self._doc_rename(d)),
                ("Delete", ft.Icons.DELETE_OUTLINE, ft.Colors.ERROR,
                 lambda d=doc: self._doc_delete(d)),
            ],
        )

    def _doc_manage_tags(self, doc):
        self._tag_manager.tag_dialog.open_for_document(doc, self.module)

    #  document dialog helpers 

    def _close_dialog(self, dlg):
        dlg.open = False
        dlg.update()

    def _doc_rename(self, doc):
        def on_rename(new_name):
            try:
                self._store.rename_document(doc, new_name)
                self._reload_current_module()
            except Exception as e:
                self.show_error(f"Rename failed: {e}")

        dlg = RenameDialog("Rename document", on_rename, initial_value=doc.title)
        self.page.overlay.append(dlg)
        self.page.update()
        dlg.open = True
        dlg.update()

    def _doc_delete(self, doc):
        def on_confirm():
            try:
                self._store.delete_document(self.module, doc)
                self._reload_current_module()
            except Exception as e:
                self.show_error(f"Delete failed: {e}")

        dlg = ConfirmDialog(
            "Delete document",
            f'Delete "{doc.title}"? This cannot be undone.',
            on_confirm
        )
        self.page.overlay.append(dlg)
        self.page.update()
        dlg.open = True
        dlg.update()

    #  file opener

    def _open_file(self, filepath: str):
        try:
            if sys.platform == "win32":
                import os
                os.startfile(filepath)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", filepath])
            else:
                subprocess.Popen(["xdg-open", filepath])
        except Exception as ex:
            print(f"Could not open {filepath}: {ex}")