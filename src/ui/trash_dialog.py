"""Trash dialog: list deleted items, restore them, or remove them forever."""

from __future__ import annotations

import flet as ft

from app_storage.app_config import AppConfig
from app_storage.module_store import ModuleStore
from app_storage.trash_store import TrashEntry, TrashStore
from app_logging import get_logger

log = get_logger(__name__)


class TrashDialog(ft.AlertDialog):
    def __init__(self, store: ModuleStore, on_changed=None, sync_service=None):
        super().__init__()
        self._store = store
        self._on_changed = on_changed
        self._sync_service = sync_service
        self._cfg = AppConfig()
        self.modal = True
        self.scrollable = True
        self.title = ft.Row(
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.DELETE_OUTLINE, size=20),
                ft.Text("Trash", size=18, weight=ft.FontWeight.BOLD),
            ],
        )
        self._list = ft.ListView(spacing=8, expand=True, height=360)
        self._empty_hint = ft.Text(
            "Trash is empty.",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self._status = ft.Text(
            "", size=12, color=ft.Colors.ON_SURFACE_VARIANT
        )
        self.content = ft.Container(
            width=560,
            content=ft.Column(
                tight=True,
                spacing=8,
                controls=[self._list, self._empty_hint, self._status],
            ),
        )
        self.actions = [
            ft.TextButton(
                "Empty trash",
                icon=ft.Icons.DELETE_SWEEP,
                on_click=self._confirm_empty,
            ),
            ft.FilledButton(
                "Close",
                icon=ft.Icons.CLOSE,
                on_click=self._close,
            ),
        ]

    # -- lifecycle --------------------------------------------------------

    def show(self) -> None:
        self._reload()
        self._status.value = ""
        self.open = True
        try:
            self.update()
        except Exception:
            pass

    def _close(self, e=None) -> None:
        self.open = False
        self.update()

    def _trash(self) -> TrashStore:
        return TrashStore(
            self._store.root,
            device_id=self._cfg.device_id,
            device_name=self._cfg.device_name,
        )

    def _reload(self) -> None:
        entries = self._trash().list_entries()
        self._list.controls.clear()
        for entry in entries:
            self._list.controls.append(self._row(entry))
        self._empty_hint.visible = not entries
        self._list.visible = bool(entries)

    def _row(self, entry: TrashEntry) -> ft.Container:
        icon = ft.Icons.FOLDER_OUTLINED if entry.kind == "module" else ft.Icons.DESCRIPTION
        when = entry.deleted_at.replace("T", " ").replace("Z", " UTC")
        detail = f"{when} · {entry.device_name or entry.device_id or 'unknown'}"
        return ft.Container(
            padding=8,
            border_radius=8,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, size=20),
                    ft.Column(
                        expand=True,
                        tight=True,
                        spacing=2,
                        controls=[
                            ft.Text(entry.original_path, weight=ft.FontWeight.W_500),
                            ft.Text(
                                detail,
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                    ),
                    ft.IconButton(
                        icon=ft.Icons.RESTORE,
                        tooltip="Restore",
                        on_click=lambda e, entry_id=entry.id: self._restore(entry_id),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_FOREVER,
                        tooltip="Delete forever",
                        icon_color=ft.Colors.ERROR,
                        on_click=lambda e, entry_id=entry.id: self._confirm_delete(entry_id),
                    ),
                ],
            ),
        )

    # -- actions ----------------------------------------------------------

    def _sync_running(self) -> bool:
        if self._sync_service is not None and self._sync_service.is_running:
            self._status.value = "Wait for the running sync to finish."
            self.update()
            return True
        return False

    def _restore(self, entry_id: str) -> None:
        if self._sync_running():
            return
        self.page.run_thread(lambda: self._restore_worker(entry_id))

    def _post(self, message: str) -> None:
        page = self.page
        if page is None:
            return
        try:
            page.run_task(self._after_change, message)
        except Exception:
            pass

    def _restore_worker(self, entry_id: str) -> None:
        try:
            target = self._trash().restore(entry_id)
            message = f"Restored: {target.name}"
        except Exception as ex:
            log.warning("trash restore failed: %s", ex)
            message = f"Restore failed: {ex}"
        self._post(message)

    def _confirm_delete(self, entry_id: str) -> None:
        self._open_confirm(
            "Delete forever?",
            "This entry is also removed on the other synced devices.",
            lambda: self._delete_forever(entry_id),
        )

    def _delete_forever(self, entry_id: str) -> None:
        if self._sync_running():
            return
        self.page.run_thread(lambda: self._delete_worker(entry_id))

    def _delete_worker(self, entry_id: str) -> None:
        try:
            self._trash().delete_forever(entry_id)
            message = "Entry deleted."
        except Exception as ex:
            log.warning("trash delete failed: %s", ex)
            message = f"Delete failed: {ex}"
        self.page.run_task(self._after_change, message)

    def _confirm_empty(self, e) -> None:
        self._open_confirm(
            "Empty the trash?",
            "All entries are also removed on the other synced devices.",
            self._empty,
        )

    def _empty(self) -> None:
        if self._sync_running():
            return
        self.page.run_thread(self._empty_worker)

    def _empty_worker(self) -> None:
        try:
            count = self._trash().empty()
            message = f"{count} entries deleted."
        except Exception as ex:
            log.warning("trash empty failed: %s", ex)
            message = f"Emptying trash failed: {ex}"
        self.page.run_task(self._after_change, message)

    async def _after_change(self, message: str) -> None:
        self._reload()
        self._status.value = message
        try:
            self.update()
        except Exception:
            pass
        if self._on_changed:
            try:
                result = self._on_changed()
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                log.debug("trash on_changed failed", exc_info=True)

    def _open_confirm(self, title: str, text: str, action) -> None:
        def close_dialog():
            dialog.open = False
            if dialog in self.page.overlay:
                self.page.overlay.remove(dialog)
            self.page.update()

        def run(e=None):
            close_dialog()
            action()

        def cancel(e=None):
            close_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(text),
            actions=[
                ft.TextButton("Cancel", on_click=cancel),
                ft.FilledButton("Delete", on_click=run),
            ],
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
