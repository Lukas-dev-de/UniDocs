"""
ui/group_home.py
----------------
Landing page for a group (and for the UniDocs root, shown as "Home").

Shown in the detail pane whenever a group is opened and no module is selected.
Right now it only shows the group name at the top - clicking it renames the
group, exactly like the module title does (except for Home, which has no folder
and cannot be renamed). The space below is reserved for group-level content
such as todos; documents are never listed here.

    home = GroupHomeDetail(store=store, on_group_renamed=cb)
    home.set_group("School")   # or None for Home
"""

import flet as ft

from app_storage.module_store import ModuleStore


@ft.control
class GroupHomeDetail(ft.Container):

    def __init__(self, store: ModuleStore, on_group_renamed=None):
        super().__init__()

        self._store = store
        self._on_group_renamed = on_group_renamed
        # Folder name of the group on screen; ``None`` = Home (UniDocs root).
        self._group: str | None = None

        #  Title: text display + inline editor 
        self.title_text = ft.Text(
            value="Home",
            size=32,
            weight=ft.FontWeight.BOLD,
            overflow=ft.TextOverflow.ELLIPSIS,
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
            on_tap=self._start_title_edit,
            mouse_cursor=ft.MouseCursor.TEXT,
            expand=True,
        )

        #  Styling mirrors ModuleDetail so switching between the two is seamless. 
        self.border_radius = 16
        self.padding = 16
        self.expand = 19
        self.bgcolor = ft.Colors.SURFACE

        self.content = ft.Column(
            spacing=10,
            expand=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            spacing=4,
                            expand=True,
                            controls=[
                                ft.Row(controls=[self._title_click, self.title_field]),
                            ],
                        ),
                    ],
                ),
                ft.Divider(color=ft.Colors.OUTLINE_VARIANT),
                # Reserved for group-level content (e.g. todos) later on.
            ],
        )

    #  public 

    def set_group(self, group: str | None):
        """Show the home page for *group* (``None`` = Home)."""
        self._group = group or None
        self._show_title_text(self._group or "Home")
        self._title_click.tooltip = "Rename group" if self._group else "Home"
        self.update()

    #  inline TITLE editing 

    async def _start_title_edit(self, e):
        if self._group is None:  # Home / root has no folder to rename
            return
        self.title_field.value = self._group
        self._title_click.visible = False
        self.title_field.visible = True
        self.update()
        await self.title_field.focus()

    def _commit_title(self, e):
        if self._group is None:
            self._show_title_text("Home")
            self.update()
            return

        new_title = (self.title_field.value or "").strip()
        if not new_title or new_title == self._group:
            self._show_title_text(self._group)
            self.update()
            return

        if self._store.group_rename_conflict(self._group, new_title):
            # Refuse rather than clobber the other folder.
            self._show_title_text(self._group)
            self.update()
            self.show_error(f'"{new_title}" already exists.')
            return

        old_name = self._group
        try:
            new_name = self._store.rename_group(old_name, new_title)
        except Exception as ex:
            print(f"Rename failed: {ex}")
            self._show_title_text(self._group)
            self.update()
            return

        # Show the stored folder name: _safe_name may have dropped characters.
        self._group = new_name
        self._show_title_text(new_name)
        self.update()
        if self._on_group_renamed:
            self._on_group_renamed(old_name, new_name)

    def _show_title_text(self, value: str):
        self.title_text.value = value
        self._title_click.visible = True
        self.title_field.visible = False

    def show_error(self, message: str):
            self.page.show_snack_bar(ft.SnackBar(content=ft.Text(message)))
