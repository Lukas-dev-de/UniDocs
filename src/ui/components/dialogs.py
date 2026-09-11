import flet as ft

class ConfirmDialog(ft.AlertDialog):
    def __init__(self, title: str, content: str, on_confirm):
        super().__init__(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(content),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close()),
                ft.FilledButton("Confirm", style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700), on_click=lambda e: self._handle_confirm(on_confirm)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._on_confirm = on_confirm

    def _handle_confirm(self, callback):
        self.close()
        callback()

    def close(self):
        self.open = False
        self.update()

class RenameDialog(ft.AlertDialog):
    def __init__(self, title: str, on_rename, initial_value=""):
        self.field = ft.TextField(label="New name", value=initial_value, expand=True)
        super().__init__(
            modal=True,
            title=ft.Text(title),
            content=ft.Container(width=360, content=self.field),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close()),
                ft.FilledButton("Rename", on_click=lambda e: self._handle_rename(on_rename)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def _handle_rename(self, callback):
        new_name = self.field.value.strip()
        if not new_name:
            self.field.error_text = "Name cannot be empty"
            self.update()
            return
        self.close()
        callback(new_name)

    def close(self):
        self.open = False
        self.update()