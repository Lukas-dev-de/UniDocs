"""
Serialization smoke test.

Flet ships controls to the client as MessagePack. Anything that msgpack cannot
encode (e.g. a bare ``set`` assigned to a control property) blows up at
``page.update()`` time, with a traceback that points at whatever happened to
trigger the flush rather than at the offending property.

This script builds the real widget tree against a throwaway UniDocs folder and
packs it exactly the way Flet does, so such mistakes surface immediately.
"""

import sys
import tempfile
from pathlib import Path

# The app package lives in <repo>/src and uses absolute imports
# (``from ui.theme import ...``), so put that directory on the path.
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import msgpack  # noqa: E402
import flet as ft  # noqa: E402
from flet.controls.base_control import BaseControl  # noqa: E402
from flet.messaging.protocol import (  # noqa: E402
    configure_encode_object_for_msgpack,
)

from app_storage.app_config import AppConfig  # noqa: E402
from app_storage.module_store import ModuleStore  # noqa: E402
from ui.components.color_selector import ColorSelector  # noqa: E402
from ui.components.module_edit_dialog import ModuleEditDialog  # noqa: E402
from ui.theme import PALETTES, ThemeManager  # noqa: E402
from ui.module_detail import ModuleDetail  # noqa: E402
from ui.module_sidebar import ModuleSidebar  # noqa: E402
from ui.settings_dialog import SettingsDialog  # noqa: E402

encode = configure_encode_object_for_msgpack(BaseControl)

failures: list[str] = []


def pack(label: str, obj) -> None:
    try:
        payload = msgpack.packb([0, obj], default=encode)
    except Exception as ex:
        failures.append(label)
        print(f"  FAIL {label}: {type(ex).__name__}: {ex}")
        return
    print(f"  ok   {label} ({len(payload)} bytes)")


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / "UniDocs"
    root.mkdir(parents=True)

    cfg = AppConfig(config_path=Path(tmp) / "config.json")
    store = ModuleStore(root=root)

    # Real module on disk (written + re-read so icon round-tripping is exercised).
    from models.module import Module

    module = Module(title="School", description="Notes", icon=ft.Icons.SCHOOL)
    store.save_module(module)
    module = store.load_all()[0]
    (root / "School" / "notes.txt").write_text("hello", encoding="utf-8")
    module = store._load_module(store._folder_for(module)) or module

    # A module with an accent colour, written and re-read from disk.
    colored = Module(
        title="Physics",
        description="Lectures",
        icon=ft.Icons.SCIENCE,
        color="#1A5FB4",
    )
    store.save_module(colored)
    colored = store._load_module(store._folder_for(colored)) or colored
    assert colored.color == "#1A5FB4", f"colour did not round-trip: {colored.color!r}"
    assert module.color is None, f"uncoloured module gained a colour: {module.color!r}"

    theme = ThemeManager(cfg)

    print("building widgets:")
    sidebar = ModuleSidebar(store=store, theme=theme)
    detail = ModuleDetail(store=store)
    dialog = SettingsDialog(store=store, theme=theme)

    dialog._mode_selector.selected = [theme.mode]
    dialog._palette_dropdown.value = theme.palette_id

    print("packing:")
    pack("ModuleSidebar", sidebar)
    pack("ModuleDetail", detail)
    pack("SettingsDialog", dialog)
    pack("module tile", sidebar._make_tile(module) if sidebar.modules_list is not None else None)
    pack("colored module tile", sidebar._make_tile(colored))
    pack("settings overlay list", ft.Column([dialog]))

    # Colour picker in both states (nothing chosen / a swatch chosen).
    print("colour selector:")
    picker = ColorSelector()
    pack("ColorSelector (empty)", picker)
    picker.set_value("#2E7D32")
    pack("ColorSelector (selected)", picker)
    picker.reset()
    assert picker.value is None

    # Module editor, populated from a real module.
    print("module edit dialog:")
    edit_dialog = ModuleEditDialog(store=store, on_saved=lambda m, p: None)
    edit_dialog.update = lambda *a, **k: None  # no page in this test
    edit_dialog.open_for(colored)
    pack("ModuleEditDialog", edit_dialog)

    # Exercise the appearance controls through their full value range.
    print("appearance controls across palettes/modes:")
    for pid in PALETTES:
        for mode in ("system", "light", "dark"):
            theme.set_palette(pid)
            theme.set_mode(mode)
            dialog._sync_mode_selector()
            dialog._sync_palette_dropdown()
            pack(f"  {pid}/{mode}", ft.Column([dialog._mode_selector, dialog._palette_dropdown]))

print()
store.stop_watching()

if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("SERIALIZATION OK")
