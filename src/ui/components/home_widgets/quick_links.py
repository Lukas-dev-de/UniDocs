"""
ui/components/home_widgets/quick_links.py
-----------------------------------------
Card with the group's quick links: websites opened in the system browser.

In edit mode the gear opens a dialog that adds, edits and removes links. Each
link keeps a name, a URL and an icon; the icon is stored by name in the
group's .home.json and falls back to a plain link icon.

    links = [{"id": ..., "label": "Moodle", "url": "https://...", "icon": "SCHOOL"}]
"""

from __future__ import annotations

import uuid

import flet as ft

from app_storage.module_store import _icon_to_name, _name_to_icon
from ui.components.home_widgets.base import HomeWidget
from ui.components.icon_selector import IconSelector

# Icon every new link starts with.
DEFAULT_LINK_ICON = "LINK"


class QuickLinksDialog(ft.AlertDialog):
    """Edits the whole quick-link list at once; Save writes it back.

    Adds its rows straight into a scrollable column (rather than faking a
    list) so that removing one is a plain control removal. Rows without a URL
    are dropped on save, so a half-filled new row is harmless.
    """

    def __init__(self, links: list[dict], on_save, on_close=None):
        self._on_save = on_save
        self._on_close = on_close
        self._rows: list[dict] = []

        self._rows_column = ft.Column(
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            height=360,
        )

        super().__init__(
            modal=True,
            title=ft.Text("Quick Links"),
            content=ft.Container(
                width=520,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        self._rows_column,
                        ft.TextButton(
                            "Link hinzufügen",
                            icon=ft.Icons.ADD,
                            on_click=self._add_row,
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda e: self.close()),
                ft.FilledButton("Speichern", on_click=self._save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        for link in links:
            if isinstance(link, dict):
                self._add_row(link=link)
        if not self._rows:
            self._add_row()

    def reset(self, links: list[dict]) -> None:
        """Rebuild the rows for a fresh edit session.

        The dialog instance is kept in the overlay and reused, so a new open
        has to drop the previous session's rows rather than build a new dialog.
        """
        self._rows = []
        self._rows_column.controls.clear()
        for link in links:
            if isinstance(link, dict):
                self._add_row(link=link)
        if not self._rows:
            self._add_row()

    #  rows 

    def _build_row(self, link: dict) -> dict:
        selector = IconSelector(icon_size=20)
        selector.set_value(_name_to_icon(link.get("icon") or DEFAULT_LINK_ICON))

        label = ft.TextField(
            label="Name", value=link.get("label", ""), dense=True, width=150
        )
        url = ft.TextField(
            label="URL", value=link.get("url", ""), dense=True, expand=True
        )
        row = ft.Row(spacing=8, controls=[selector, label, url])
        entry = {
            "id": link.get("id") or str(uuid.uuid4()),
            "selector": selector,
            "label": label,
            "url": url,
            "control": row,
        }
        row.controls.append(
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                tooltip="Entfernen",
                on_click=lambda e, en=entry: self._remove_row(en),
            )
        )
        return entry

    def _add_row(self, e=None, link=None):
        entry = self._build_row(link or {})
        self._rows.append(entry)
        self._rows_column.controls.append(entry["control"])
        self._safe_update(self._rows_column)

    def _remove_row(self, entry: dict):
        if entry in self._rows:
            self._rows.remove(entry)
        if entry["control"] in self._rows_column.controls:
            self._rows_column.controls.remove(entry["control"])
        self._safe_update(self._rows_column)

    #  save 

    def _collect(self) -> list[dict]:
        links = []
        for entry in self._rows:
            url = (entry["url"].value or "").strip()
            if not url:
                continue
            label = (entry["label"].value or "").strip() or url
            icon = entry["selector"].value
            links.append(
                {
                    "id": entry["id"],
                    "label": label,
                    "url": url,
                    "icon": _icon_to_name(icon) if icon else DEFAULT_LINK_ICON,
                }
            )
        return links

    def _save(self, e=None):
        self._on_save(self._collect())
        self.close()

    #  helpers 

    def _safe_update(self, control):
        try:
            control.update()
        except RuntimeError:
            pass

    def close(self):
        self.open = False
        self._safe_update(self)
        if self._on_close:
            self._on_close(self)


@ft.control
class QuickLinksWidget(HomeWidget):
    TITLE = "Quick Links"
    TYPE = "quick_links"

    def __init__(self, store, module_store=None, on_open_module=None):
        super().__init__(store, module_store, on_open_module)
        # Built once on first open, then kept in the overlay and reused.
        self._dialog = None

    def refresh(self):
        links = [
            link
            for link in self._store.load(self._group).get("quick_links", [])
            if isinstance(link, dict) and link.get("url")
        ]
        self.body.controls.clear()
        if not links:
            self.body.controls.append(self.placeholder("Noch keine Links."))
            return
        self.body.controls.append(
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=8,
                controls=[self._link_tile(link) for link in links],
            )
        )

    def _link_tile(self, link: dict) -> ft.Container:
        icon = _name_to_icon(link.get("icon") or DEFAULT_LINK_ICON)
        return ft.Container(
            content=ft.Row(
                spacing=8,
                controls=[
                    ft.Icon(icon, size=18, color=ft.Colors.PRIMARY),
                    ft.Text(link.get("label") or link["url"], size=13),
                ],
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=10,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            ink=True,
            tooltip=link["url"],
            on_click=lambda e, url=link["url"]: self._open(url),
        )

    def _open(self, url: str):
        page = self._page()
        if page is None:
            return
        page.run_task(self._launch, url)

    async def _launch(self, url: str):
        await ft.UrlLauncher().launch_url(url)

    #  settings 

    def open_settings(self, e=None):
        page = self._page()
        if page is None:
            return
        if self._dialog is None:
            self._dialog = QuickLinksDialog(
                [],
                on_save=self._save_links,
                on_close=self._close_dialog,
            )
            page.overlay.append(self._dialog)
        self._dialog.reset(self._store.load(self._group).get("quick_links", []))
        self._dialog.open = True
        page.update()

    def _save_links(self, links: list[dict]):
        self._store.set_quick_links(self._group, links)
        self.refresh()
        self.update()

    def _close_dialog(self, dialog):
        # Hide only - a dialog pulled out of the overlay makes Flutter complain
        # about a removed view. The instance is reused on the next open.
        dialog.open = False
        page = self._page()
        if page is not None:
            page.update()

