from __future__ import annotations
import os
import sys
"""
Startup flow changes:
 - On first run, prompt user for the libvips folder (root or bin) and save it to tileCutter_settings.json.
 - On subsequent runs, read the saved path, set PATH to its bin folder, then import pyvips.
"""


# ONLY ADD CODE BELOW THIS COMMENT
# Raise Qt image I/O allocation cap BEFORE importing any PyQt6 modules
os.environ["QT_IMAGEIO_MAXALLOC"] = str(2 * 1024 * 1024 * 1024)  # 2 GiB

from typing import List, Optional, Dict, Tuple
from pathlib import Path
import json
import tempfile
from PyQt6.QtWidgets import (
	QApplication,
	QFileDialog,
	QDialog,
	QVBoxLayout,
	QHBoxLayout,
	QLabel,
	QLineEdit,
	QPushButton,
	QMessageBox,
)
from PyQt6.QtGui import QPixmap, QImageReader
from PyQt6.QtCore import QSize

import app_ui
try:
	# Raise reader-level allocation cap to 2 GiB as well
	QImageReader.setAllocationLimit(2048)  # in megabytes
except Exception:
	pass

# Global pyvips module - will be imported after PATH is configured
pyvips = None


# Embedded zoom levels table (in place of reading zoom_levels.json)
# Source equivalent of dist/zoom_levels.json
ZOOM_LEVELS_DATA = {
	"levels": [
		{"name": "zoom 0 (256x256)", "width": 256, "height": 256},
		{"name": "zoom 1 (512x512)", "width": 512, "height": 512},
		{"name": "zoom 2 (1024x1024)", "width": 1024, "height": 1024},
		{"name": "zoom 3 (2048x2048)", "width": 2048, "height": 2048},
		{"name": "zoom 4 (4096x4096)", "width": 4096, "height": 4096},
		{"name": "zoom 5 (8192x8192)", "width": 8192, "height": 8192},
		{"name": "zoom 6 (16384x16384)", "width": 16384, "height": 16384},
		{"name": "zoom 7 (32768x32768)", "width": 32768, "height": 32768},
	]
}


def _update_command_previews(window: app_ui.MainWindow) -> None:
	"""Update live preview of image and tiles commands in the UI, if present."""
	try:
		if not hasattr(window, "preview_image") and not hasattr(window, "preview_tiles"):
			return
	except Exception:
		return

	def _build_image_cmd() -> str:
		try:
			img = getattr(window, "output_image", None) or getattr(window, "loaded_image_vips", None)
			if img is None:
				return "No image loaded."
			src_path = getattr(window, "loaded_image_path", None) or "<in-memory>"
			fmt = get_selected_file_type(window)
			q = get_selected_quality(window)
			try:
				w_pixels, h_pixels = int(img.width), int(img.height)
			except Exception:
				return f"Image loaded from {src_path} (size unknown)"
			# Estimate effective format as in save_image
			req = (fmt or "png").lower()
			if req == "webp" and (w_pixels >= 16384 or h_pixels >= 16384):
				eff = "png"
			elif req in ("jpg", "jpeg") and (w_pixels >= 65536 or h_pixels >= 65536):
				eff = "png"
			else:
				eff = "jpg" if req in ("jpg", "jpeg") else req
			# Compute quality/compression options
			if eff == "png":
				comp = int(round((100 - q) * 9 / 99))
				comp = max(0, min(9, comp))
				return f"pyvips.pngsave(<image>, 'output.{eff}', compression={comp}, strip=True)  # from {src_path}"
			if eff == "webp":
				return f"pyvips.webpsave(<image>, 'output.webp', Q={q}, strip=True)  # from {src_path}"
			if eff == "jpg":
				return f"pyvips.jpegsave(<image>, 'output.jpg', Q={q}, strip=True)  # from {src_path}"
			return f"pyvips.pngsave(<image>, 'output.png', strip=True)  # from {src_path}"
		except Exception as e:
			return f"(Error building command preview: {str(e)[:40]})"

	def _build_tiles_cmd() -> str:
		try:
			img = getattr(window, "output_image", None)
			if img is None:
				return "No image + zoom level selected."
			src_path = getattr(window, "loaded_image_path", None) or "<in-memory composite>"
			# Base name & zoom suffix
			if getattr(window, "loaded_image_path", None):
				base_name = os.path.splitext(os.path.basename(window.loaded_image_path))[0]
			else:
				base_name = "tiles"
			try:
				zidx_val = int(window.zoom_levels.currentIndex()) - 1
				zoom_part = f"-Zoom-{zidx_val}" if zidx_val >= 0 else ""
			except Exception:
				zoom_part = ""
			# Target dir (may be default or placeholder)
			chosen_dir = ""
			try:
				if hasattr(window, "tiles_output_dir_input") and window.tiles_output_dir_input:
					chosen_dir = window.tiles_output_dir_input.text().strip()
			except Exception:
				chosen_dir = ""
			if not chosen_dir:
				base_dir = os.path.dirname(getattr(window, "loaded_image_path", "")) or os.path.expanduser("~")
				chosen_dir = os.path.join(base_dir, "<tiles-output>")
			base_path = os.path.join(chosen_dir, f"{base_name}{zoom_part}")
			# Layout
			try:
				layout = window.layout_options.value.lower().strip() or "dz"
			except Exception:
				layout = "dz"
			# Tile size (always used)
			try:
				tile_size = int(getattr(window, "tile_size_value", None).value)
			except Exception:
				tile_size = 256
			# File type / suffix
			fmt = get_selected_file_type(window)
			q = get_selected_quality(window)
			if fmt == "webp":
				suffix = f".webp[Q={q}]"
			elif fmt in ("jpg", "jpeg"):
				suffix = f".jpg[Q={q}]"
			else:
				comp = int(round((100 - q) * 9 / 99))
				comp = max(0, min(9, comp))
				suffix = f".png[compression={comp}]"
			# Optional flags
			parts = [
				"vips dzsave",
				str(src_path),
				str(base_path),
				"--centre",
				"--depth onetile",
				"--background 0",
				f"--tile-size {tile_size}",
				f"--layout {layout}",
				f"--suffix '{suffix}'",
			]
			# Overlap
			try:
				if getattr(window, "change_overlap", None) and window.change_overlap.isChecked():
					parts.append(f"--overlap {int(window.change_overlap_value.value)}")
			except Exception:
				pass
			# region_shrink
			try:
				if getattr(window, "change_region_shrink", None) and window.change_region_shrink.isChecked():
					mode = (window.change_region_shrink_mode.value or "mode").lower()
					parts.append(f"--region-shrink {mode}")
			except Exception:
				pass
			# skip_blanks
			try:
				if getattr(window, "skip_blanks", None) and window.skip_blanks.isChecked():
					parts.append(f"--skip-blanks {int(window.skip_blanks_value.value)}")
			except Exception:
				pass
			return " ".join(parts)
		except Exception as e:
			return f"(Error building tiles preview: {str(e)[:40]})"

	try:
		if hasattr(window, "preview_image"):
			window.preview_image.setText(_build_image_cmd())
		if hasattr(window, "preview_tiles"):
			window.preview_tiles.setText(_build_tiles_cmd())
	except Exception:
		pass


def load_zoom_levels_table() -> List[dict]:
	"""Return table of zoom levels using embedded data.

	Returns list of dicts: {"name": str, "size": int} where size is max(width, height).
	"""
	try:
		levels = (ZOOM_LEVELS_DATA or {}).get("levels") or []
		table: List[dict] = []
		for i, lv in enumerate(levels):
			name = str(lv.get("name", f"zoom {i}"))
			w = int(lv.get("width", 0) or 0)
			h = int(lv.get("height", 0) or 0)
			size = max(w, h)
			if size <= 0:
				continue
			table.append({"name": name, "size": size})
		if not table:
			raise ValueError("no valid levels in embedded data")
		return table
	except Exception as e:
		print("Failed to use embedded zoom levels, using defaults:", e)
		defaults = [256, 512, 1024, 2048, 4096]
		return [{"name": f"zoom {i} ({s}x{s})", "size": s} for i, s in enumerate(defaults)]


def get_selected_zoom_level(window: app_ui.MainWindow) -> Optional[dict]:
	"""Return selected zoom level dict or None if placeholder selected."""
	try:
		idx = window.zoom_levels.currentIndex()
		if idx <= 0:
			return None
		return window.zoom_levels_table[idx - 1]
	except Exception:
		return None


def _ensure_zoom_selected(window: app_ui.MainWindow) -> bool:
	"""Warn and return False if the placeholder 'Choose zoom level' is selected."""
	try:
		if int(window.zoom_levels.currentIndex()) > 0:
			return True
	except Exception:
		pass
	try:
		# Use the in-app banner and auto-hide after 3s
		window.show_done_banner("Please choose a Zoom level", 3000)
	except Exception:
		print("Please choose a Zoom level before generating images or tiles.")
	return False


def auto_select_zoom_for_image(window: app_ui.MainWindow, img_w: int, img_h: int) -> None:
	"""Pick the smallest zoom whose square can contain the image and select it."""
	if not hasattr(window, "zoom_levels_table"):
		return
	max_side = max(int(img_w), int(img_h))
	sel_index = None
	for i, lv in enumerate(window.zoom_levels_table):
		if lv["size"] >= max_side:
			sel_index = i
			break
	if sel_index is None:
		sel_index = len(window.zoom_levels_table) - 1
	try:
		window.zoom_levels.blockSignals(True)
		window.zoom_levels.setCurrentIndex(sel_index + 1)  # +1 for placeholder
	finally:
		window.zoom_levels.blockSignals(False)


def make_transparent_square(size: int):
	"""Create a transparent RGBA square of given size using pyvips."""
	if pyvips is None:
		raise RuntimeError("pyvips not initialized")
	return pyvips.Image.black(size, size, bands=4)  # RGBA all zeros => transparent


def ensure_rgba(img):
	"""Return an RGBA image. Replicates/joins bands as needed."""
	if pyvips is None:
		raise RuntimeError("pyvips not initialized")
	b = img.bands
	out = img
	try:
		if b == 4:
			return out
		if b == 3:
			return out.addalpha()  # RGB -> RGBA
		if b == 2:
			g = out.extract_band(0)
			a = out.extract_band(1)
			rgb = pyvips.Image.bandjoin([g, g, g])
			return pyvips.Image.bandjoin([rgb, a])
		if b == 1:
			rgb = pyvips.Image.bandjoin([out, out, out])
			return rgb.addalpha()
		if b > 4:
			rgb = out.extract_band(0, n=3)
			return rgb.addalpha()
	except Exception as e:
		print("Failed to coerce image to RGBA:", e)
	try:
		return out.addalpha()
	except Exception:
		return out


def compose_centered(square, img):
	"""Insert img centered into square (both RGBA), returning composite image."""
	if pyvips is None:
		raise RuntimeError("pyvips not initialized")
	base = square
	src = ensure_rgba(img)
	side = base.width  # square assumed
	left = max((side - src.width) // 2, 0)
	top = max((side - src.height) // 2, 0)
	return base.insert(src, left, top, expand=False)


def make_fitting_image(window: app_ui.MainWindow, src, square_side: int):
	"""Return an image that fits entirely within square_side without upscaling.

	Prefers libvips thumbnail-on-load for memory efficiency when the original
	file path is available; otherwise falls back to a high-quality resize.
	"""
	if pyvips is None:
		raise RuntimeError("pyvips not initialized")
	max_side = max(src.width, src.height)
	if max_side <= square_side:
		return src
	# Try to re-load efficiently from file using thumbnail
	spath = getattr(window, "loaded_image_path", None)
	if spath and os.path.isfile(spath):
		try:
			# Fit within the square, preserving aspect ratio (no crop)
			timg = pyvips.Image.thumbnail(spath, square_side, height=square_side)
			return timg
		except Exception as e:
			print("thumbnail() failed, falling back to resize:", e)
	# Fallback: resize current image down to fit
	scale = square_side / float(max_side)
	try:
		return src.resize(scale, kernel="lanczos3")
	except Exception:
		return src.resize(scale)


def recompute_image_pipeline(window: app_ui.MainWindow) -> None:
	"""Recompute the composited image pipeline based on selection and loaded image.

	Produces lightweight pyvips.Image graphs only (no in-memory encoded buffers):
	- window.square_buffer: pyvips.Image (transparent square)
	- window.output_image: pyvips.Image (composited)
	"""
	print("recompute_image_pipeline: starting")
	sel = get_selected_zoom_level(window)
	if not sel:
		print("recompute_image_pipeline: no zoom level selected, clearing buffers")
		# clear when no selection
		for attr in ("square_buffer", "output_image", "output_buffer"):
			if hasattr(window, attr):
				try:
					delattr(window, attr)
				except Exception:
					pass
		return

	size = int(sel["size"])
	print(f"recompute_image_pipeline: zoom size = {size}")
	try:
		square = make_transparent_square(size)
		setattr(window, "square_buffer", square)
		print(f"recompute_image_pipeline: created square buffer {size}x{size}")
	except Exception as e:
		print("Failed to create square buffer:", e)
		import traceback
		traceback.print_exc()
		return

	src_img = getattr(window, "loaded_image_vips", None)
	if src_img is None:
		print("recompute_image_pipeline: no source image loaded")
		for attr in ("output_image", "output_buffer"):
			if hasattr(window, attr):
				try:
					delattr(window, attr)
				except Exception:
					pass
		return

	print(f"recompute_image_pipeline: source image {src_img.width}x{src_img.height}")
	try:
		# Downscale if the selected square is smaller than the image
		fitted = make_fitting_image(window, src_img, size)
		print(f"recompute_image_pipeline: fitted image {fitted.width}x{fitted.height}")
		composite = compose_centered(square, fitted)
		print(f"recompute_image_pipeline: composite created {composite.width}x{composite.height}")
		setattr(window, "output_image", composite)
		# Ensure any legacy buffer attributes are cleared
		if hasattr(window, "output_buffer"):
			try:
				delattr(window, "output_buffer")
			except Exception:
				pass
	except Exception as e:
		print("Failed to compose centered image:", e)
		import traceback
		traceback.print_exc()
		for attr in ("output_image", "output_buffer"):
			if hasattr(window, attr):
				try:
					delattr(window, attr)
				except Exception:
					pass
	# Refresh command previews when the pipeline changes
	try:
		_update_command_previews(window)
	except Exception:
		pass

def get_output_image(window: app_ui.MainWindow) -> Optional["pyvips.Image"]:
	"""Return the current composited image, recomputing the pipeline if needed."""
	try:
		img = getattr(window, "output_image", None)
		if img is not None:
			return img
		# recompute if possible
		if getattr(window, "loaded_image_vips", None) is None:
			return None
		try:
			if int(window.zoom_levels.currentIndex()) <= 0:
				return None
		except Exception:
			return None
		recompute_image_pipeline(window)
		return getattr(window, "output_image", None)
	except Exception:
		return None

def is_image_file(path: str) -> bool:
	ext = os.path.splitext(path)[1].lower()
	return ext in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif")


def _build_output_base(window: app_ui.MainWindow) -> Dict[str, str]:
	"""Return a dict with base name/dir and zoom suffix for current selection.

	Keys: base_name, base_dir (from source or home), zoom_part
	"""
	src_path = getattr(window, "loaded_image_path", None)
	if src_path:
		base_dir = os.path.dirname(src_path) or os.path.expanduser("~")
		base_name = os.path.splitext(os.path.basename(src_path))[0]
	else:
		base_dir = os.path.expanduser("~")
		base_name = "output"
	try:
		zidx_val = int(window.zoom_levels.currentIndex()) - 1
		zoom_part = f"-Zoom-{zidx_val}" if zidx_val >= 0 else ""
	except Exception:
		zoom_part = ""
	return {"base_name": base_name, "base_dir": base_dir, "zoom_part": zoom_part}


def load_image_to_buffer(window: app_ui.MainWindow, path: str) -> None:
	"""Load image bytes into window.loaded_image_bytes and display in viewer.

	We keep a bytes buffer on the window for later processing and call
	the UI method to set the image for display.
	"""
	print(f"Loading image from: {path}")
	# Record path and decode with pyvips directly from file
	setattr(window, "loaded_image_path", path)
	try:
		if pyvips is None:
			error_msg = "pyvips not initialized - libvips may not be configured correctly"
			print(f"ERROR: {error_msg}")
			raise RuntimeError(error_msg)
		print(f"pyvips module available: {pyvips}")
		# Prefer random access for JPEGs to avoid out-of-order read issues later
		ext = os.path.splitext(path)[1].lower()
		access_mode = "random" if ext in (".jpg", ".jpeg") else "sequential"
		print(f"Loading with access mode: {access_mode}")
		# Try to load with autorotate first (for formats that support it)
		# If that fails, try without autorotate (for formats like WebP that don't support it)
		try:
			img = pyvips.Image.new_from_file(path, access=access_mode, autorotate=True)
			print(f"Image loaded with autorotate")
		except Exception as e:
			if "does not support optional argument autorotate" in str(e):
				print(f"Format doesn't support autorotate, loading without it...")
				img = pyvips.Image.new_from_file(path, access=access_mode)
			else:
				raise
		print(f"Image loaded successfully: {img.width}x{img.height}, bands={img.bands}")
		setattr(window, "loaded_image_vips", img)
		print("Auto-selecting zoom level...")
		auto_select_zoom_for_image(window, img.width, img.height)
		print("Recomputing image pipeline...")
		recompute_image_pipeline(window)
		print("Image loading complete!")
	except Exception as e:
		print(f"Failed to decode/process image with pyvips: {e}")
		import traceback
		traceback.print_exc()
		try:
			window.show_done_banner(f"Error loading image: {str(e)[:50]}", 5000)
		except Exception:
			pass

	# Display: use QImageReader with scaled decode from file path (no in-memory buffers)
	try:
		viewer_size = getattr(window, "image_viewer", None).size() if hasattr(window, "image_viewer") else QSize(0, 0)
		max_w = viewer_size.width() or 2048
		max_h = viewer_size.height() or 2048
		reader = QImageReader(path)
		reader.setAutoTransform(True)
		orig = reader.size()
		if orig.isValid():
			w, h = orig.width(), orig.height()
			ratio = min(max_w / max(1, w), max_h / max(1, h))
			ratio = min(1.0, ratio)
			target = QSize(max(1, int(w * ratio)), max(1, int(h * ratio)))
			reader.setScaledSize(target)
		img_q = reader.read()
		if not img_q.isNull():
			pm = QPixmap.fromImage(img_q)
			if hasattr(window.image_viewer, "_pixmap"):
				window.image_viewer._pixmap = pm
				window.image_viewer._update_view()
			else:
				window.image_viewer.set_image(path)
		else:
			# fallback: try loading pixmap directly
			pm = QPixmap(path)
			if not pm.isNull() and hasattr(window.image_viewer, "_pixmap"):
				window.image_viewer._pixmap = pm
				window.image_viewer._update_view()
			else:
				window.image_viewer.set_image(path)
	except Exception as e:
		print("Failed to display image:", e)
	# Update previews after loading a new image
	try:
		_update_command_previews(window)
	except Exception:
		pass


def open_file_dialog(window: app_ui.MainWindow) -> None:
	"""Open a native file dialog and load the selected image."""
	fname, _ = QFileDialog.getOpenFileName(
		None,
		"Open Image",
		os.path.expanduser("~"),
		"Images (*.png *.jpg *.jpeg *.webp *.tif *.tiff *.bmp *.gif);;All Files (*)",
	)
	if fname:
		load_image_to_buffer(window, fname)


def handle_dropped_paths(window: app_ui.MainWindow, paths: List[str]) -> None:
	"""Handle paths dropped onto the viewer; choose first valid image file."""
	for p in paths:
		if os.path.isfile(p) and is_image_file(p):
			load_image_to_buffer(window, p)
			return
	# if none matched, try first file
	if paths:
		first = paths[0]
		if os.path.isfile(first):
			load_image_to_buffer(window, first)


def get_selected_file_type(window: app_ui.MainWindow) -> str:
	try:
		ft = window.file_type.value.lower().strip()
		if ft in ("jpeg", "jpg"):
			return "jpg"
		if ft in ("png", "webp"):
			return ft
	except Exception:
		pass
	return "png"


def get_selected_quality(window: app_ui.MainWindow) -> int:
	try:
		q = int(window.image_quality.value)
		return max(1, min(100, q))
	except Exception:
		return 100


def save_image(img, path: str, requested_fmt: str, quality: int) -> Tuple[str, str]:
	"""Save image using streaming encoders with format fallback and extension fix.

	- Accepts a requested format (png/webp/jpg), but will fallback to PNG if the
	  image exceeds encoder limits (e.g., WebP ~16k, JPEG ~65k).
	- Ensures the file extension matches the final effective format.
	- Returns (final_path, effective_format).
	"""
	if pyvips is None:
		raise RuntimeError("pyvips not initialized")
	req = (requested_fmt or "png").lower()
	w, h = int(img.width), int(img.height)
	# Compute effective format considering size limits
	if req == "webp" and (w >= 16384 or h >= 16384):
		print("Requested WebP but image is too large; falling back to PNG.")
		eff = "png"
	elif req in ("jpg", "jpeg") and (w >= 65536 or h >= 65536):
		print("Requested JPEG but image is too large; falling back to PNG.")
		eff = "png"
	else:
		eff = "jpg" if req in ("jpg", "jpeg") else req

	# Normalize extension to match effective format
	root, ext = os.path.splitext(path)
	desired_ext = ".jpg" if eff == "jpg" else f".{eff}"
	if not ext or ext.lower() != desired_ext:
		path = root + desired_ext

	if eff == "png":
		comp = int(round((100 - quality) * 9 / 99))
		comp = max(0, min(9, comp))
		rgba = ensure_rgba(img)
		rgba.pngsave(path, compression=comp, strip=True)
		return path, eff
	elif eff == "webp":
		rgba = ensure_rgba(img)
		rgba.webpsave(path, Q=quality, strip=True)
		return path, eff
	elif eff == "jpg":
		base = img
		if img.bands == 4:
			try:
				base = img.flatten(background=[255, 255, 255])
			except Exception:
				base = img.extract_band(0, n=3)
		elif img.bands > 3:
			base = img.extract_band(0, n=3)
		elif img.bands < 3:
			g = img.extract_band(0)
			base = pyvips.Image.bandjoin([g, g, g])
		base.jpegsave(path, Q=quality, strip=True)
		return path, eff
	else:
		# Default fallback to PNG
		rgba = ensure_rgba(img)
		rgba.pngsave(path, strip=True)
		return path, eff


## removed: save_output_image_to_file (merged into save_image)

def _unique_path(base_path: str) -> str:
	"""Return a unique path by appending _N if needed (up to 9999)."""
	if not os.path.exists(base_path):
		return base_path
	counter = 1
	while counter < 10000:
		candidate = f"{base_path}_{counter}"
		if not os.path.exists(candidate):
			return candidate
		counter += 1
	# As a last resort, include a timestamp
	import time
	return f"{base_path}_{int(time.time())}"


def _compute_tiles_output_dir(window: app_ui.MainWindow) -> Optional[str]:
	"""Compute the tiles output directory: '<image name>_tiles' next to the source image.

	Returns an absolute path string or None if no source path is available.
	"""
	src_path = getattr(window, "loaded_image_path", None)
	if not src_path:
		return None
	base_dir = os.path.dirname(src_path) or os.path.expanduser("~")
	base_name = os.path.splitext(os.path.basename(src_path))[0]
	out_dir = os.path.join(base_dir, f"{base_name}_tiles")
	# Ensure the path is unique by appending a counter if the directory exists
	candidate = out_dir
	counter = 1
	while os.path.exists(candidate):
		candidate = f"{out_dir}_{counter}"
		counter += 1
		if counter > 9999:
			break
	return candidate


class VipshomeSetupDialog(QDialog):
	"""Small dialog to choose the libvips folder (root or bin) and save it.

	Accepts either:
	- path to the root libvips folder containing a 'bin' subfolder, or
	- path directly to the 'bin' folder.
	"""

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setWindowTitle("Locate libvips folder")
		self.resize(560, 160)
		layout = QVBoxLayout(self)
		hint = QLabel(
			"Select your libvips folder.\n"
			"You can choose the root (e.g. C:\\vips-dev-8.17) or the bin folder directly."
		)
		layout.addWidget(hint)
		row = QHBoxLayout()
		self.path_edit = QLineEdit(self)
		self.path_edit.setPlaceholderText(r"C:\\Users\\You\\Downloads\\vips-dev-8.17")
		browse = QPushButton("Browse…", self)
		row.addWidget(self.path_edit, 1)
		row.addWidget(browse)
		layout.addLayout(row)
		buttons = QHBoxLayout()
		self.save_btn = QPushButton("Save && Continue", self)
		cancel_btn = QPushButton("Cancel", self)
		self.save_btn.setDefault(True)
		buttons.addStretch(1)
		buttons.addWidget(cancel_btn)
		buttons.addWidget(self.save_btn)
		layout.addLayout(buttons)

		browse.clicked.connect(self._browse)
		self.save_btn.clicked.connect(self._on_save)
		cancel_btn.clicked.connect(self.reject)

	def _browse(self):
		base = os.path.expanduser("~")
		chosen = QFileDialog.getExistingDirectory(self, "Select libvips folder (root or bin)", base)
		if chosen:
			self.path_edit.setText(chosen)

	@staticmethod
	def derive_bin_dir(path_text: str) -> str:
		p = (path_text or "").strip().strip('"')
		if not p:
			return ""
		# If user picked the bin folder directly
		if os.path.isdir(p) and os.path.basename(p).lower() == "bin":
			return p
		# If user picked the root, use its bin
		candidate = os.path.join(p, "bin")
		if os.path.isdir(candidate):
			return candidate
		return ""

	def _on_save(self):
		bin_dir = self.derive_bin_dir(self.path_edit.text())
		if not bin_dir:
			QMessageBox.warning(
				self,
				"Invalid path",
				"Please choose the libvips folder (root with a 'bin' subfolder) or the 'bin' folder itself.",
			)
			return
		self._selected_bin = bin_dir
		self.accept()

	def selected_bin(self) -> Optional[str]:
		return getattr(self, "_selected_bin", None)


def _settings_path() -> Path:
	return _app_dir() / "tileCutter_settings.json"


def _app_dir() -> Path:
	# When frozen by PyInstaller (one-file), write next to the executable.
	try:
		if getattr(sys, "frozen", False) and hasattr(sys, "executable"):
			return Path(sys.executable).resolve().parent
	except Exception:
		pass
	# Fallback to the script directory during development
	"""Return the application directory for settings and outputs.

	- When frozen with PyInstaller (onefile), use the directory of the .exe,
	  not the temporary extraction folder. This makes the build portable and
	  keeps tileCutter_settings.json and output folders next to the exe.
	- When running from source, use the folder containing this file.
	"""
	try:
		if getattr(sys, "frozen", False):  # PyInstaller/Freezer
			# sys.executable points to the .exe path; its parent is the exe dir
			return Path(sys.executable).resolve().parent
	except Exception:
		pass
	return Path(__file__).resolve().parent


def _ensure_app_default_dirs() -> Dict[str, str]:
	"""Ensure default output directories exist under the app directory.

	Returns a dict with keys default_image_output_dir and default_tiles_output_dir.
	"""
	img_dir = _app_dir() / "tileCutter-images"
	tiles_dir = _app_dir() / "tileCutter-tiles"
	try:
		os.makedirs(img_dir, exist_ok=True)
	except Exception:
		pass
	try:
		os.makedirs(tiles_dir, exist_ok=True)
	except Exception:
		pass
	return {
		"default_image_output_dir": str(img_dir),
		"default_tiles_output_dir": str(tiles_dir),
	}


def _load_settings_any() -> Dict[str, str]:
	try:
		with open(_settings_path(), "r", encoding="utf-8") as f:
			data = json.load(f) or {}
			# Keep only simple values
			return {k: str(v) for k, v in data.items() if isinstance(v, (str, int))}
	except Exception:
		return {}


def _save_settings_merge(updates: Dict[str, str]) -> None:
	data = _load_settings_any()
	data.update({k: str(v) for k, v in (updates or {}).items()})
	try:
		with open(_settings_path(), "w", encoding="utf-8") as f:
			json.dump(data, f, indent=2)
	except Exception:
		pass


def _ensure_libvips_and_import_pyvips(app: QApplication) -> None:
	"""Ensure we have a valid libvips bin path; set PATH and import pyvips.

	If not configured, show a small dialog to capture the path and persist it.
	"""
	print("=== libvips initialization ===")
	# 1) Try settings
	s = _load_settings_any()
	raw = s.get("libvips_bin", "").strip()
	print(f"Settings path: {_settings_path()}")
	print(f"Stored libvips_bin: {raw}")
	bin_dir = raw
	if not (bin_dir and os.path.isdir(bin_dir)):
		print(f"Stored path not valid, trying to derive...")
		# Maybe user stored the root path previously
		bin_dir = VipshomeSetupDialog.derive_bin_dir(raw)
		print(f"Derived bin_dir: {bin_dir}")
	# 2) If not valid, prompt user once
	if not (bin_dir and os.path.isdir(bin_dir)):
		print("No valid libvips path found, showing setup dialog...")
		dlg = VipshomeSetupDialog()
		if dlg.exec() != QDialog.DialogCode.Accepted:
			# User cancelled: exit app cleanly
			print("User cancelled libvips setup, exiting.")
			sys.exit(0)
		sel = dlg.selected_bin()
		if not sel:
			print("No path selected, exiting.")
			sys.exit(0)
		bin_dir = sel
		print(f"User selected: {bin_dir}")
		_save_settings_merge({"libvips_bin": bin_dir})
	# 3) Prepend to PATH and import pyvips
	print(f"Adding to PATH: {bin_dir}")
	os.environ["PATH"] = bin_dir + ";" + os.environ.get("PATH", "")
	print(f"Current PATH: {os.environ['PATH'][:200]}...")
	# Import pyvips only now, after PATH is set
	print("Importing pyvips...")
	global pyvips
	import pyvips  # type: ignore
	print(f"pyvips imported successfully: {pyvips}")
	print(f"pyvips version: {pyvips.version(0)}.{pyvips.version(1)}.{pyvips.version(2)}")
	print("=== libvips initialization complete ===\n")


def main():
	app = QApplication(sys.argv)
	# ensure libvips is configured and pyvips is importable
	_ensure_libvips_and_import_pyvips(app)
	# apply the same stylesheet as the UI file
	app.setStyleSheet(app_ui.QSS_TEMPLATE)

	w = app_ui.MainWindow()

	# ---------- settings: load/save default output folders ----------
	SETTINGS_PATH = _settings_path()

	def _load_settings() -> Dict[str, str]:
		# Merge app default dirs into settings if not already set
		s = _load_settings_any()
		defaults = _ensure_app_default_dirs()
		changed = False
		for k, v in defaults.items():
			if not s.get(k):
				s[k] = v
				changed = True
		if changed:
			_save_settings_merge({k: s[k] for k in defaults.keys()})
		return s

	def _apply_settings_to_ui():
		s = _load_settings()
		try:
			if hasattr(w, "image_output_dir_input"):
				w.image_output_dir_input.setText(s.get("default_image_output_dir", ""))
		except Exception:
			pass
		try:
			if hasattr(w, "tiles_output_dir_input"):
				w.tiles_output_dir_input.setText(s.get("default_tiles_output_dir", ""))
		except Exception:
			pass

	def _save_settings_from_ui():
		try:
			data = {
				"default_image_output_dir": getattr(w, "image_output_dir_input", None).text().strip()
				if hasattr(w, "image_output_dir_input") and w.image_output_dir_input else "",
				"default_tiles_output_dir": getattr(w, "tiles_output_dir_input", None).text().strip()
				if hasattr(w, "tiles_output_dir_input") and w.tiles_output_dir_input else "",
			}
			_save_settings_merge(data)
		except Exception:
			pass

	_apply_settings_to_ui()

	# Load zoom levels from JSON and populate dropdown
	w.zoom_levels_table = load_zoom_levels_table()
	try:
		zoom_names = [lvl["name"] for lvl in w.zoom_levels_table]
		w.zoom_levels.set_items(["Choose zoom level"] + zoom_names)
	except Exception as e:
		print("Failed to set zoom levels in dropdown:", e)

	# React to zoom level changes from the dropdown
	def on_zoom_changed(_index: int):
		try:
			recompute_image_pipeline(w)
		except Exception as e:
			print("Failed to refresh buffers on zoom change:", e)
		try:
			_update_command_previews(w)
		except Exception:
			pass

	w.zoom_levels.currentIndexChanged.connect(on_zoom_changed)

	# wire signals: click opens dialog, drop loads path(s)
	w.image_viewer.openFileRequested.connect(lambda: open_file_dialog(w))
	w.image_viewer.pathsDropped.connect(lambda paths: handle_dropped_paths(w, paths))

	# Wire browse buttons for default output directories
	def _choose_default_dir(kind: str):
		src_path = getattr(w, "loaded_image_path", None)
		start_dir = os.path.dirname(src_path) if src_path else os.path.expanduser("~")
		chosen = QFileDialog.getExistingDirectory(None, "Choose default output folder", start_dir)
		if not chosen:
			return
		try:
			if kind == "image" and hasattr(w, "image_output_dir_input"):
				w.image_output_dir_input.setText(chosen)
			if kind == "tiles" and hasattr(w, "tiles_output_dir_input"):
				w.tiles_output_dir_input.setText(chosen)
			_save_settings_from_ui()
		except Exception:
			pass

	try:
		if hasattr(w, "image_output_dir_browse"):
			w.image_output_dir_browse.clicked.connect(lambda: _choose_default_dir("image"))
		if hasattr(w, "tiles_output_dir_browse"):
			w.tiles_output_dir_browse.clicked.connect(lambda: _choose_default_dir("tiles"))
		if hasattr(w, "image_output_dir_input"):
			w.image_output_dir_input.textChanged.connect(lambda _t: _save_settings_from_ui())
		if hasattr(w, "tiles_output_dir_input"):
			w.tiles_output_dir_input.textChanged.connect(lambda _t: _save_settings_from_ui())
	except Exception:
		pass

	# Live command preview: recompute when relevant controls change
	def _wire_preview_updates():
		try:
			_update_command_previews(w)
		except Exception:
			pass
		# File/image related controls
		try:
			w.file_type.currentIndexChanged.connect(lambda _i: _wire_preview_updates())
		except Exception:
			pass
		try:
			w.image_quality.valueChanged.connect(lambda _v: _wire_preview_updates())
		except Exception:
			pass
		try:
			w.layout_options.currentIndexChanged.connect(lambda _i: _wire_preview_updates())
		except Exception:
			pass
		# Tile size
		try:
			w.tile_size_value.valueChanged.connect(lambda _v: _wire_preview_updates())
		except Exception:
			pass
		# Optional dzsave options
		try:
			w.change_overlap.toggled.connect(lambda _b: _wire_preview_updates())
		except Exception:
			pass
		try:
			w.change_overlap_value.valueChanged.connect(lambda _v: _wire_preview_updates())
		except Exception:
			pass
		try:
			w.change_region_shrink.toggled.connect(lambda _b: _wire_preview_updates())
		except Exception:
			pass
		try:
			w.change_region_shrink_mode.currentIndexChanged.connect(lambda _i: _wire_preview_updates())
		except Exception:
			pass
		try:
			w.skip_blanks.toggled.connect(lambda _b: _wire_preview_updates())
		except Exception:
			pass
		try:
			w.skip_blanks_value.valueChanged.connect(lambda _v: _wire_preview_updates())
		except Exception:
			pass
		# Default output dirs text
		try:
			w.image_output_dir_input.textChanged.connect(lambda _t: _wire_preview_updates())
		except Exception:
			pass
		try:
			w.tiles_output_dir_input.textChanged.connect(lambda _t: _wire_preview_updates())
		except Exception:
			pass

	try:
		_wire_preview_updates()
	except Exception:
		pass

	# Hook Generate Image button: use default directory when set, otherwise prompt
	def on_generate_image_clicked():
		# Validate zoom selection first
		if not _ensure_zoom_selected(w):
			return
		# Indicate processing start in the top banner
		try:
			w.show_processing_banner("Image processing")
			QApplication.processEvents()
		except Exception:
			pass
		
		output_img = get_output_image(w)
		if output_img is None:
			print("No output image available. Load an image and select a zoom level.")
			try:
				w.show_done_banner("Image processing done", 3000)
			except Exception:
				pass
			return
		requested_fmt = get_selected_file_type(w)
		quality = get_selected_quality(w)
		# Try default image output directory first
		default_dir = ""
		try:
			if hasattr(w, "image_output_dir_input") and w.image_output_dir_input:
				default_dir = w.image_output_dir_input.text().strip()
		except Exception:
			default_dir = ""

		filter_map = {
			"png": "PNG Image (*.png)",
			"jpg": "JPEG Image (*.jpg *.jpeg)",
			"webp": "WebP Image (*.webp)",
		}
		# Build default filename from input with Zoom and _transparentBG suffix
		src_path = getattr(w, "loaded_image_path", None)
		try:
			zidx_val = int(w.zoom_levels.currentIndex()) - 1
			zoom_part = f"-Zoom-{zidx_val}" if zidx_val >= 0 else ""
		except Exception:
			zoom_part = ""
		if src_path:
			base = os.path.splitext(os.path.basename(src_path))[0]
			initial_dir = os.path.dirname(src_path) or os.path.expanduser("~")
			initial_name = f"{base}{zoom_part}_transparentBG.{('jpg' if requested_fmt == 'jpg' else requested_fmt)}"
			initial_path = os.path.join(initial_dir, initial_name)
		else:
			initial_path = os.path.join(os.path.expanduser("~"), f"output{zoom_part}_transparentBG.{('jpg' if requested_fmt == 'jpg' else requested_fmt)}")
		if default_dir:
			try:
				os.makedirs(default_dir, exist_ok=True)
				base = os.path.splitext(os.path.basename(src_path))[0] if src_path else "output"
				fname = os.path.join(default_dir, f"{base}{zoom_part}_transparentBG.{requested_fmt}")
				saved, eff = save_image(output_img, fname, requested_fmt, quality)
				print(f"Saved image to: {saved}")
				# Show fallback banner or generic done banner (avoid overwrite)
				try:
					if requested_fmt.lower() == "webp" and eff != "webp":
						w.show_done_banner("Image too big for .webp format, saving as .png instead", 4000)
					else:
						w.show_done_banner("Image processing done", 3000)
				except Exception:
					pass
				return
			except Exception as e:
				print("Default image folder failed, falling back to Save As dialog:", e)

		# No default folder set or failed: Ask where to save
		selected_filter = filter_map.get(requested_fmt, "All Files (*)")
		fname, _ = QFileDialog.getSaveFileName(
			None,
			"Save Image",
			initial_path,
			";;".join(filter_map.values()) + ";;All Files (*)",
			selected_filter,
		)
		if not fname:
			return
		try:
			saved, eff = save_image(output_img, fname, requested_fmt, quality)
			print(f"Saved image to: {saved}")
			# Show fallback banner or generic done banner (avoid overwrite)
			try:
				if requested_fmt.lower() == "webp" and eff != "webp":
					w.show_done_banner("Image too big for .webp format, saving as .png instead", 4000)
				else:
					w.show_done_banner("Image processing done", 3000)
			except Exception:
				pass
		except Exception as e:
			print(f"Failed to save image: {e}")
			try:
				w.show_done_banner(f"Error saving image: {str(e)[:50]}", 5000)
			except Exception:
				pass

	w.generate_image.clicked.connect(on_generate_image_clicked)

	# Hook Generate Tiles button: use default directory when set, otherwise prompt
	def on_generate_tiles_clicked():
		# Validate zoom selection first
		if not _ensure_zoom_selected(w):
			return
		# Indicate processing start in the top banner
		try:
			w.show_processing_banner("Image processing")
			QApplication.processEvents()
		except Exception:
			pass
		
		output_img = getattr(w, "output_image", None)
		if output_img is None:
			print("No output image available. Load an image and select a zoom level.")
			try:
				w.show_done_banner("Image processing done", 3000)
			except Exception:
				pass
			return
		src_path = getattr(w, "loaded_image_path", None)
		# Try default tiles output directory first
		chosen_dir = ""
		try:
			if hasattr(w, "tiles_output_dir_input") and w.tiles_output_dir_input:
				chosen_dir = w.tiles_output_dir_input.text().strip()
		except Exception:
			chosen_dir = ""
		if chosen_dir:
			try:
				os.makedirs(chosen_dir, exist_ok=True)
			except Exception as e:
				print("Failed to create default tiles folder, opening chooser:", e)
				chosen_dir = ""
		if not chosen_dir:
			# Ask user where to save tiles: choose a parent folder
			start_dir = os.path.dirname(src_path) if src_path else os.path.expanduser("~")
			chosen_dir = QFileDialog.getExistingDirectory(None, "Choose folder to save tiles", start_dir)
			if not chosen_dir:
				print("Tile generation cancelled.")
				try:
					w.statusBar().showMessage("Image processing done", 3000)
				except Exception:
					pass
				return
		# Compute a clean base path for dzsave without suffixes
		base_name = os.path.splitext(os.path.basename(src_path))[0] if src_path else "tiles"
		try:
			zidx_val = int(w.zoom_levels.currentIndex()) - 1
			zoom_part = f"-Zoom-{zidx_val}" if zidx_val >= 0 else ""
		except Exception:
			zoom_part = ""
		base_path = os.path.join(chosen_dir, f"{base_name}{zoom_part}")
		# User-configurable options needed for naming
		# Inline tiles parameters from UI
		try:
			layout = w.layout_options.value.lower().strip()
			layout = layout or "dz"
		except Exception:
			layout = "dz"
		target_dir = os.path.join(chosen_dir, f"{base_name}{zoom_part}-tiles-{layout}")

		# Fixed options – always passed to dzsave
		try:
			# tile_size is always used, but user can change its value
			tile_size = int(getattr(w, "tile_size_value", None).value)
		except Exception:
			# fallback to vips default commonly used size
			tile_size = 256
		fixed_opts = {
			"centre": True,
			"depth": "onetile",
			"background": 0,
			"tile_size": tile_size,
		}
		# User-configurable options
		# Suffix depends on selected file type and quality
		fmt = get_selected_file_type(w)
		q = get_selected_quality(w)
		if fmt == "webp":
			suffix = f".webp[Q={q}]"
		elif fmt in ("jpg", "jpeg"):
			suffix = f".jpg[Q={q}]"
		else:
			comp = int(round((100 - q) * 9 / 99))
			comp = max(0, min(9, comp))
			suffix = f".png[compression={comp}]"
		# Overlap (optional) – added only when checkbox is enabled
		overlap = None
		try:
			if getattr(w, "change_overlap", None) and w.change_overlap.isChecked():
				overlap = int(w.change_overlap_value.value)
		except Exception:
			overlap = None
		# region_shrink (optional)
		region_shrink = None
		try:
			if getattr(w, "change_region_shrink", None) and w.change_region_shrink.isChecked():
				region_shrink = (w.change_region_shrink_mode.value or "mode").lower()
		except Exception:
			region_shrink = None
		# skip_blanks (optional)
		skip_blanks = None
		try:
			if getattr(w, "skip_blanks", None) and w.skip_blanks.isChecked():
				skip_blanks = int(w.skip_blanks_value.value)
		except Exception:
			skip_blanks = None

		# dzsave will create the final tiles folder(s) based on layout and base_path
		try:
			# Determine final directory (unique) and base path for dzsave
			final_dir = _unique_path(target_dir)
			if layout == "dz":
				# dz creates '<base>_files' + '<base>.dzi' -> we rename to final_dir
				base_for_dzsave = os.path.join(chosen_dir, f"{base_name}{zoom_part}")
			else:
				# other layouts write directly into the base directory
				base_for_dzsave = final_dir

			# Build dzsave options: required + optional flags
			dz_opts = dict(fixed_opts)
			dz_opts.update({
				"layout": layout,
				"suffix": suffix,
			})
			if overlap is not None:
				dz_opts["overlap"] = overlap
			if region_shrink is not None:
				dz_opts["region_shrink"] = region_shrink
			if skip_blanks is not None:
				dz_opts["skip_blanks"] = skip_blanks
			# Stream directly from the composited pipeline
			output_img.dzsave(
				base_for_dzsave,
				**dz_opts,
			)
			# For dz, move '<base>_files' to final_dir and include '.dzi' file
			created_dir = None
			extra_files = []
			if layout == "dz":
				created_dir = f"{base_for_dzsave}_files"
				if not os.path.isdir(created_dir):
					raise RuntimeError("dzsave output folder not found")
				dzi = f"{base_for_dzsave}.dzi"
				if os.path.isfile(dzi):
					extra_files.append(dzi)
			else:
				# For non-dz layouts, dzsave wrote directly to final_dir
				created_dir = final_dir

			# Move/rename only for dz layout; non-dz already wrote to final_dir
			if layout == "dz":
				if created_dir and os.path.isdir(created_dir):
					try:
						os.replace(created_dir, final_dir)
					except Exception:
						# Fallback to shutil.move for cross-device moves
						import shutil
						shutil.move(created_dir, final_dir)
					# Move any extra files (e.g., .dzi) into final_dir
					for ef in extra_files:
						try:
							base_name_only = os.path.basename(ef)
							os.replace(ef, os.path.join(final_dir, base_name_only))
						except Exception:
							try:
								import shutil
								shutil.move(ef, os.path.join(final_dir, base_name_only))
							except Exception:
								pass
					print(f"Tiles generated in: {final_dir}")
				else:
					print("Tiles generated but output folder not detected.")
			else:
				# Non-dz layouts already used final_dir as output
				print(f"Tiles generated in: {final_dir}")
			try:
				w.show_done_banner("Tiles generated successfully", 3000)
			except Exception:
				pass
		except Exception as e:
			print("Failed to generate tiles:", e)
			try:
				w.show_done_banner(f"Error generating tiles: {str(e)[:50]}", 5000)
			except Exception:
				pass

	try:
		w.generate_tiles.clicked.connect(on_generate_tiles_clicked)
	except Exception:
		pass
	# Reset button clears the in-memory buffer and resets the viewer
	def _reset():
		# Use simple assignments to clear state
		w.loaded_image_bytes = None
		w.loaded_image_vips = None
		w.loaded_image_path = None
		w.square_buffer = None
		w.output_image = None
		w.output_buffer = None
		# reset zoom dropdown to default (placeholder)
		try:
			w.zoom_levels.setCurrentIndex(0)
		except Exception:
			pass
		# clear viewer internal pixmap and update view
		try:
			if hasattr(w.image_viewer, "_pixmap"):
				w.image_viewer._pixmap = None
				w.image_viewer._update_view()
		except Exception as e:
			print("Failed to reset viewer:", e)

	try:
		w.reset.clicked.connect(_reset)
	except Exception:
		# If reset button missing for some reason, ignore
		pass

	w.resize(1024, 640)
	w.show()

	sys.exit(app.exec())


if __name__ == "__main__":
	main()