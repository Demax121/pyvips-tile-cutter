# Tile Cutter UI (no logic)

This UI defines the widgets and styling only. No signals or behavior are implemented yet.

## Components and names

- Main window class: `MainWindow`
- Image viewer placeholder: `self.image_viewer` (QFrame)
  - Purpose: target for future drag-and-drop or click-to-open image.
- Dropdown: `self.zoom_levels` (ValueComboBox)
  - Name: `"zoom_levels"`
  - Access current selection: `window.zoom_levels.value`
  - Initial items: `InitialData.zoom_levels`
- Composite zoom level widget: `self.zoom_level` (ZoomLevelWidget)
  - Text input: `self.zoom_level.zoom_level_name` (QLineEdit)
  - Integer input: `self.zoom_level.square_size` (QSpinBox) with label "square size"
- Dropdown: `self.file_type` (ValueComboBox)
  - Name: `"file_type"`
  - Access current selection: `window.file_type.value`
  - Initial items: `InitialData.file_types` (defaults: `webp`, `png`)
- Buttons (UI only, no behavior):
  - `self.generate_image` (text: "Generate image")
  - `self.generate_tiles` (text: "Generate tiles")

## Easy styling (theme)

Edit the `THEME` dict in `app_ui.py` to change look and feel:

```python
THEME = {
    "font": "Segoe UI",
    "bg": "#1f1f1f",
    "panel": "#232323",
    "panelAlt": "#26292e",
    "text": "#eaeaea",
    "muted": "#b7c0c8",
    "accent": "#e6f0ff",
    "primary": "#3b82f6",
    "primaryDark": "#1d4ed8",
    "primaryHover": "#60a5fa",
    "border": "#2e2e2e",
    "radius": 8,
    "spacing": 10,
    "padding": "8px 12px",
}
```

The stylesheet `QSS_TEMPLATE` uses those tokens. For example, to make buttons square:

```python
"border-radius": 0
```

To style specific parts:
- Title label uses `QLabel#title`
- Panels use `QFrame.panel` (set via `setProperty("class", "panel")`)
- Viewer uses `QFrame.viewer`
- Muted labels use `QLabel[role="muted"]`
- Buttons can use variants via property: `button.setProperty("variant", "secondary")`

## Changing dropdown items

- Zoom levels: edit `InitialData.zoom_levels` in `app_ui.py`.
- File types: edit `InitialData.file_types` (defaults: `webp`, `png`).

At runtime, you can also replace items:

```python
window.zoom_levels.set_items(["Low", "Med", "High", "Ultra"])
window.file_type.set_items(["webp", "png", "jpeg"])  # UI only
```

## Accessing values (when you add logic later)

```python
name = window.zoom_level.zoom_level_name.text()
size = window.zoom_level.square_size.value()
zoom_choice = window.zoom_levels.value  # same as currentText()
fmt = window.file_type.value
```

## Layout overview

- Top: Title
- Middle: Two columns
  - Left: Image viewer placeholder
  - Right: Controls panel
    - Zoom levels dropdown
    - Zoom level composite (name + square size)
    - File type dropdown
    - Buttons row (Generate image / Generate tiles)

## Notes

- The UI intentionally has no behavior. Hook up your logic later (e.g., connect buttons, implement drag & drop) without changing the layout or styling.
- Keep QSS selectors stable by preserving object names and properties.