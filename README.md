# pyvips-tile-cutter

A small desktop tool for generating square, transparent-background images and DeepZoom-style tiles from large source images. It uses libvips via `pyvips` for fast, low‑memory image processing and a modern PyQt6 GUI for an easy workflow.

The app lets you:
- Load an image (drag & drop or file picker)
- Choose a target “zoom level” (square size) to fit your image inside without upscaling
- Export a centered, transparent square image as PNG/WebP/JPG
- Generate DeepZoom tiles with selectable layouts (dz, google, zoomify, iiif) and options


## What’s in this repo

- `tile-cutter.py` — The main application. Wires the UI to the processing logic (pyvips), handles file dialogs, exporting images, and generating tiles.
- `app_ui.py` — UI only. A modern PyQt6 interface with drag-and-drop image viewer and controls for zoom, format, quality, tile layout, and optional parameters.
- `tileCutter_settings.json` — Saved defaults for output folders (auto-created/updated by the app).
- `libvips/` — Windows libvips runtime bundled for convenience; the app prepends `libvips\bin` to PATH at startup so pyvips can find the DLLs.
- `images/` — Example output structure (tiles), not required to run.


## Requirements

Python
- Python 3.9+ (tested with 3.10/3.11)

Python packages
- `pyvips` (libvips Python bindings)
- `PyQt6` (GUI)

System/libvips
- Windows: libvips is bundled under `libvips/`. No extra install needed if you run the app from the project root.
- macOS/Linux: install libvips from your package manager, then install `pyvips`:
	- macOS (Homebrew): `brew install vips`
	- Debian/Ubuntu: `sudo apt-get install -y libvips`
	- Fedora: `sudo dnf install vips`

Note: pyvips needs to find the libvips shared library at runtime. On Windows, `tile-cutter.py` sets `PATH` to include `libvips\bin`. On macOS/Linux, ensure libvips is installed system-wide or is otherwise discoverable (e.g., via `LD_LIBRARY_PATH` or `DYLD_LIBRARY_PATH` if using a non-default install).


## Installation

1) (Recommended) Create and activate a virtual environment.
2) Install the Python dependencies:

```
pip install pyvips PyQt6
```

On macOS/Linux, make sure you’ve installed the system libvips first (see Requirements).


## How to run

From the project root:

```
python tile-cutter.py
```

On first run, a small dialog will prompt you to select your libvips folder (either the root like `C:\\vips-dev-8.17` or its `bin` subfolder). The chosen path is saved to `tileCutter_settings.json` under the key `libvips_bin`. Subsequent runs skip this dialog.

This launches the full app (UI + processing). You can also run the UI-only scaffold for design/testing:

```
python app_ui.py
```

The UI-only window won’t export images or tiles; it’s useful to tweak layout and controls.


## Using the app

Load an image
- Drag and drop an image onto the viewer, or click the viewer to open a file dialog.

Pick your options
- Zoom Levels: choose the square dimension to fit your image inside (no upscaling).
- File Type: PNG, WebP, or JPG for the exported single image.
- Quality: used for PNG (mapped to compression), WebP (Q), and JPG (Q). The UI enables this for PNG/WebP; JPG also uses a quality value internally.
- Layout Options (for tiles): `dz`, `google`, `zoomify`, `iiif`.
- Optional parameters (tiles):
	- Overlap (default 2)
	- Region shrink mode (default `mode`; options: mode, mean, median, max, min, nearest)
	- Skip blanks threshold (default 5)

Default output folders
- You can set default folders for “Generate Image” and “Generate Tiles.” These defaults are saved to `tileCutter_settings.json` in the repo folder.

Export
- Generate Image: creates a transparent square with your image centered and saves it in the selected format.
- Generate Tiles: creates DeepZoom tiles using libvips `dzsave` with your chosen layout and options.

Output naming
- Image: if a default folder is set, the filename is derived from the source name with `_transparentBG` suffix. Otherwise you’ll be prompted where to save.
- Tiles: output goes to a folder named `<image-name>-tiles-<layout>` inside the chosen directory. If a folder already exists, a numeric suffix is added to keep it unique.

Large image safeguards
- WebP encoders typically fail above ~16383 px per side; the app automatically falls back to PNG when needed.
- JPEG typically fails above ~65535 px per side; the app falls back to PNG if exceeded.
- The app prefers streaming/thumbnailing operations from libvips to avoid huge RAM spikes.


