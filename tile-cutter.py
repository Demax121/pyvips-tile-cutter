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

from typing import List, Optional, Dict
from pathlib import Path
import json
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


def get_selected_zoom_index(window: app_ui.MainWindow) -> Optional[int]:
	"""Return zero-based zoom level index or None if not selected."""
	try:
		idx = int(window.zoom_levels.currentIndex()) - 1
		if idx < 0:
			return None
		if hasattr(window, "zoom_levels_table") and 0 <= idx < len(window.zoom_levels_table):
			return idx
	except Exception:
		pass
	return None


def _is_zoom_selected(window: app_ui.MainWindow) -> bool:
	try:
		return int(window.zoom_levels.currentIndex()) > 0
	except Exception:
		return False


def _ensure_zoom_selected(window: app_ui.MainWindow) -> bool:
	"""Warn and return False if the placeholder 'Choose zoom level' is selected."""
	if _is_zoom_selected(window):
		return True
	try:
		QMessageBox.warning(
			None,
			"Zoom level required",
			"Please choose a Zoom level before generating images or tiles.",
		)
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


def make_transparent_square(size: int) -> pyvips.Image:
	"""Create a transparent RGBA square of given size using pyvips."""
	return pyvips.Image.black(size, size, bands=4)  # RGBA all zeros => transparent


def ensure_rgba(img: pyvips.Image) -> pyvips.Image:
	"""Return an RGBA image. Replicates/joins bands as needed."""
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


def compose_centered(square: pyvips.Image, img: pyvips.Image) -> pyvips.Image:
	"""Insert img centered into square (both RGBA), returning composite image."""
	base = square
	src = ensure_rgba(img)
	side = base.width  # square assumed
	left = max((side - src.width) // 2, 0)
	top = max((side - src.height) // 2, 0)
	return base.insert(src, left, top, expand=False)


def make_fitting_image(window: app_ui.MainWindow, src: pyvips.Image, square_side: int) -> pyvips.Image:
	"""Return an image that fits entirely within square_side without upscaling.

	Prefers libvips thumbnail-on-load for memory efficiency when the original
	file path is available; otherwise falls back to a high-quality resize.
	"""
	max_side = max(src.width, src.height)
	if max_side <= square_side:
		return src
	# Try to re-load efficiently from file using thumbnail
	spath = getattr(window, "loaded_image_path", None)
	if spath and os.path.isfile(spath):
		try:
			# Fit within the square, preserving aspect ratio
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


def refresh_buffers(window: app_ui.MainWindow) -> None:
	"""Recompute square_buffer and output_buffer based on selection and loaded image.

	Produces:
	- window.square_buffer: pyvips.Image (transparent square)
	- window.output_image: pyvips.Image (composited)
	- window.output_buffer: bytes (PNG-encoded composite)
	"""
	sel = get_selected_zoom_level(window)
	if not sel:
		# clear when no selection
		for attr in ("square_buffer", "output_image", "output_buffer"):
			if hasattr(window, attr):
				try:
					delattr(window, attr)
				except Exception:
					pass
		return

	size = int(sel["size"])
	try:
		square = make_transparent_square(size)
		setattr(window, "square_buffer", square)
	except Exception as e:
		print("Failed to create square buffer:", e)
		return

	src_img: Optional[pyvips.Image] = getattr(window, "loaded_image_vips", None)
	if src_img is None:
		for attr in ("output_image", "output_buffer"):
			if hasattr(window, attr):
				try:
					delattr(window, attr)
				except Exception:
					pass
		return

	try:
		# Downscale if the selected square is smaller than the image
		fitted = make_fitting_image(window, src_img, size)
		composite = compose_centered(square, fitted)
		setattr(window, "output_image", composite)
		# Do not create in-memory encoded buffers here; keep only the composed image
		if hasattr(window, "output_buffer"):
			try:
				delattr(window, "output_buffer")
			except Exception:
				pass
	except Exception as e:
		print("Failed to compose centered image:", e)
		for attr in ("output_image", "output_buffer"):
			if hasattr(window, attr):
				try:
					delattr(window, attr)
				except Exception:
					pass


def is_image_file(path: str) -> bool:
	ext = os.path.splitext(path)[1].lower()
	return ext in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif")


def load_image_to_buffer(window: app_ui.MainWindow, path: str) -> None:
	"""Load image bytes into window.loaded_image_bytes and display in viewer.

	We keep a bytes buffer on the window for later processing and call
	the UI method to set the image for display.
	"""
	# Record path and decode with pyvips directly from file
	setattr(window, "loaded_image_path", path)
	try:
		# Prefer random access for JPEGs to avoid out-of-order read issues later
		ext = os.path.splitext(path)[1].lower()
		access_mode = "random" if ext in (".jpg", ".jpeg") else "sequential"
		img = pyvips.Image.new_from_file(path, access=access_mode)
		setattr(window, "loaded_image_vips", img)
		auto_select_zoom_for_image(window, img.width, img.height)
		refresh_buffers(window)
	except Exception as e:
		print("Failed to decode/process image with pyvips:", e)

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


def encode_output_image(img: pyvips.Image, fmt: str, quality: int) -> bytes:
	"""Encode img to bytes in the requested format using quality where applicable.

	- png: map quality(1..100) to compression(9..0), keeping alpha
	- webp: use Q=quality, keep alpha
	- jpg: use Q=quality, flatten alpha to white background
	"""
	fmt = fmt.lower()

	def _save_with_retry(image: pyvips.Image, method_name: str, *args, **kwargs):
		try:
			return getattr(image, method_name)(*args, **kwargs)
		except Exception as e1:
			# Retry by materializing to memory to avoid out-of-order read errors
			try:
				mem = image.copy_memory()
				return getattr(mem, method_name)(*args, **kwargs)
			except Exception:
				raise e1
	if fmt == "png":
		# Map quality to PNG compression (inverse relation)
		comp = int(round((100 - quality) * 9 / 99))
		comp = max(0, min(9, comp))
		rgba = ensure_rgba(img)
		return _save_with_retry(rgba, "pngsave_buffer", compression=comp)
	if fmt == "webp":
		rgba = ensure_rgba(img)
		return _save_with_retry(rgba, "webpsave_buffer", Q=quality)
	if fmt in ("jpg", "jpeg"):
		# JPEG does not support alpha; flatten over white background
		base = img
		if img.bands == 4:
			try:
				base = img.flatten(background=[255, 255, 255])
			except Exception:
				# Fallback: drop alpha (results in black where transparent)
				base = img.extract_band(0, n=3)
		elif img.bands > 3:
			base = img.extract_band(0, n=3)
		elif img.bands < 3:
			# expand to RGB
			g = img.extract_band(0)
			base = pyvips.Image.bandjoin([g, g, g])
		return _save_with_retry(base, "jpegsave_buffer", Q=quality)
	# default png
	rgba = ensure_rgba(img)
	return _save_with_retry(rgba, "pngsave_buffer")


def choose_effective_format(img: pyvips.Image, requested_fmt: str) -> str:
	"""Return a safe output format considering encoder dimension limits.

	- WebP fails above ~16383 px per side; fallback to PNG when exceeded.
	- JPEG typically fails above ~65535 px per side; fallback to PNG when exceeded.
	"""
	fmt = (requested_fmt or "png").lower()
	w, h = int(img.width), int(img.height)
	# WebP constraint
	if fmt == "webp" and (w >= 16384 or h >= 16384):
		print("Requested WebP but image is too large for WebP; falling back to PNG.")
		return "png"
	# JPEG constraint
	if fmt in ("jpg", "jpeg") and (w >= 65536 or h >= 65536):
		print("Requested JPEG but image is too large for JPEG; falling back to PNG.")
		return "png"
	return fmt


def save_output_image_to_file(img: pyvips.Image, path: str, fmt: str, quality: int) -> None:
	"""Save image directly to a file using streaming encoders to avoid RAM spikes."""
	fmt = fmt.lower()
	def _save_with_retry(image: pyvips.Image, method_name: str, *args, **kwargs):
		try:
			return getattr(image, method_name)(*args, **kwargs)
		except Exception as e1:
			try:
				mem = image.copy_memory()
				return getattr(mem, method_name)(*args, **kwargs)
			except Exception:
				raise e1
	if fmt == "png":
		comp = int(round((100 - quality) * 9 / 99))
		comp = max(0, min(9, comp))
		rgba = ensure_rgba(img)
		_save_with_retry(rgba, "pngsave", path, compression=comp)
		return
	if fmt == "webp":
		rgba = ensure_rgba(img)
		_save_with_retry(rgba, "webpsave", path, Q=quality)
		return
	if fmt in ("jpg", "jpeg"):
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
		_save_with_retry(base, "jpegsave", path, Q=quality)
		return
	# default png
	rgba = ensure_rgba(img)
	_save_with_retry(rgba, "pngsave", path)

def _get_tiles_layout(window: app_ui.MainWindow) -> str:
	"""Return dzsave layout string from UI, defaulting to 'dz'."""
	try:
		layout = window.layout_options.value.lower().strip()
		return layout or "dz"
	except Exception:
		return "dz"


def _get_tiles_suffix(window: app_ui.MainWindow) -> str:
	"""Return dzsave suffix string based on file type and quality.

	Example results:
	- .webp[Q=85]
	- .jpg[Q=90]
	- .png[compression=3]
	Falls back to webp if UI is unavailable.
	"""
	# Decide effective format for tiles: follow selected file type
	fmt = get_selected_file_type(window)
	q = get_selected_quality(window)
	if fmt == "webp":
		return f".webp[Q={q}]"
	if fmt in ("jpg", "jpeg"):
		return f".jpg[Q={q}]"
	# png: map quality to compression 0..9 (0 = none/fast, 9 = max)
	comp = int(round((100 - q) * 9 / 99))
	comp = max(0, min(9, comp))
	return f".png[compression={comp}]"


def _get_tiles_overlap(window: app_ui.MainWindow) -> int:
	"""Return tile overlap. Default 2; use UI value only if checkbox checked."""
	try:
		if getattr(window, "change_overlap", None) and window.change_overlap.isChecked():
			return int(window.change_overlap_value.value)
	except Exception:
		pass
	return 2


def _get_tiles_region_shrink(window: app_ui.MainWindow) -> str:
	"""Return region_shrink mode. Default 'mode'; use UI value only if checkbox checked."""
	try:
		if getattr(window, "change_region_shrink", None) and window.change_region_shrink.isChecked():
			val = window.change_region_shrink_mode.value
			return (val or "mode").lower()
	except Exception:
		pass
	return "mode"


def _get_tiles_skip_blanks(window: app_ui.MainWindow) -> int:
	"""Return skip_blanks threshold. Default 5; use UI value only if checkbox checked."""
	try:
		if getattr(window, "skip_blanks", None) and window.skip_blanks.isChecked():
			return int(window.skip_blanks_value.value)
	except Exception:
		pass
	return 5


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
	return Path(__file__).resolve().parent / "tileCutter_settings.json"


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
	# 1) Try settings
	s = _load_settings_any()
	raw = s.get("libvips_bin", "").strip()
	bin_dir = raw
	if not (bin_dir and os.path.isdir(bin_dir)):
		# Maybe user stored the root path previously
		bin_dir = VipshomeSetupDialog.derive_bin_dir(raw)
	# 2) If not valid, prompt user once
	if not (bin_dir and os.path.isdir(bin_dir)):
		dlg = VipshomeSetupDialog()
		if dlg.exec() != QDialog.DialogCode.Accepted:
			# User cancelled: exit app cleanly
			sys.exit(0)
		sel = dlg.selected_bin()
		if not sel:
			sys.exit(0)
		bin_dir = sel
		_save_settings_merge({"libvips_bin": bin_dir})
	# 3) Prepend to PATH and import pyvips
	os.environ["PATH"] = bin_dir + ";" + os.environ.get("PATH", "")
	# Import pyvips only now, after PATH is set
	global pyvips
	import pyvips  # type: ignore


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
		return _load_settings_any()

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
			refresh_buffers(w)
		except Exception as e:
			print("Failed to refresh buffers on zoom change:", e)

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
		
		output_img = getattr(w, "output_image", None)
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
		zidx = get_selected_zoom_index(w)
		zoom_part = f"-Zoom-{zidx}" if zidx is not None else ""
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
				# Decide the actual format to use (fallback to PNG if too large for codec)
				fmt = choose_effective_format(output_img, requested_fmt)
				base = os.path.splitext(os.path.basename(src_path))[0] if src_path else "output"
				fname = os.path.join(default_dir, f"{base}{zoom_part}_transparentBG.{('jpg' if fmt == 'jpg' else fmt)}")
				save_output_image_to_file(output_img, fname, fmt, quality)
				print(f"Saved image to: {fname}")
				try:
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
		# Decide the actual format to use (fallback to PNG if too large for codec)
		fmt = choose_effective_format(output_img, requested_fmt)
		# Ensure extension matches effective format if user omitted or used different ext
		root, ext = os.path.splitext(fname)
		if not ext:
			fname = root + (".jpg" if fmt == "jpg" else f".{fmt}")
		else:
			ext_no_dot = ext[1:].lower()
			if (fmt == "jpg" and ext_no_dot not in ("jpg", "jpeg")) or (fmt != "jpg" and ext_no_dot != fmt):
				# replace mismatched extension
				fname = root + (".jpg" if fmt == "jpg" else f".{fmt}")
		try:
			save_output_image_to_file(output_img, fname, fmt, quality)
			print(f"Saved image to: {fname}")
		finally:
			try:
				w.show_done_banner("Image processing done", 3000)
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
		zidx = get_selected_zoom_index(w)
		zoom_part = f"-Zoom-{zidx}" if zidx is not None else ""
		base_path = os.path.join(chosen_dir, f"{base_name}{zoom_part}")
		# User-configurable options needed for naming
		layout = _get_tiles_layout(w)
		target_dir = os.path.join(chosen_dir, f"{base_name}{zoom_part}-tiles-{layout}")

		# Fixed options
		fixed_opts = {
			"centre": True,
			"depth": "onetile",
			"background": 0,
			"tile_size": 256,
		}
		# User-configurable options
		suffix = _get_tiles_suffix(w)
		overlap = _get_tiles_overlap(w)
		region_shrink = _get_tiles_region_shrink(w)
		skip_blanks = _get_tiles_skip_blanks(w)

		# dzsave will create the final tiles folder(s) based on layout and base_path
		try:
			def _do_dzsave(img_to_save: pyvips.Image):
				img_to_save.dzsave(
					base_path,
					layout=layout,
					suffix=suffix,
					overlap=overlap,
					region_shrink=region_shrink,
					skip_blanks=skip_blanks,
					**fixed_opts,
				)
			# Attempt with memory-backed image first to maximize success
			try:
				mem = output_img.copy_memory()
				_do_dzsave(mem)
			except Exception as e1:
				# Rebuild composite from random-access source and retry once more
				try:
					spath = getattr(w, "loaded_image_path", None)
					if spath and os.path.isfile(spath):
						# Recreate output image using a fresh random-access decode
						img2 = pyvips.Image.new_from_file(spath, access="random")
						# Regenerate buffers with this source
						try:
							setattr(w, "loaded_image_vips", img2)
							# Keep current zoom selection; rebuild composite
							refresh_buffers(w)
							new_out = getattr(w, "output_image", None)
							if new_out is not None:
								mem2 = new_out.copy_memory()
								_do_dzsave(mem2)
							else:
								raise e1
						except Exception:
							raise e1
						# restore original loaded_image_vips if needed is not critical here
					else:
						raise e1
				except Exception:
					raise e1
			# Determine likely created folder based on layout
			candidates = []
			if layout == "dz":
				candidates = [f"{base_path}_files", base_path]
			elif layout == "google":
				candidates = [f"{base_path}_tiles", base_path]
			else:
				candidates = [base_path, f"{base_path}_tiles", f"{base_path}_files"]

			created_dir = None
			for c in candidates:
				if os.path.isdir(c):
					created_dir = c
					break

			# If not found, scan chosen_dir for a recent directory starting with base_name (with zoom)
			if created_dir is None:
				try:
					import time
					latest = (None, -1.0)
					with os.scandir(chosen_dir) as it:
						for entry in it:
							if entry.is_dir() and entry.name.startswith(f"{base_name}{zoom_part}"):
								mtime = entry.stat().st_mtime
								if mtime > latest[1]:
									latest = (entry.path, mtime)
					if latest[0]:
						created_dir = latest[0]
				except Exception:
					pass

			# Compute a unique target '<name>-tiles-<layout>' directory
			final_dir = target_dir
			if os.path.exists(final_dir):
				counter = 1
				while os.path.exists(f"{final_dir}_{counter}") and counter < 10000:
					counter += 1
				final_dir = f"{final_dir}_{counter}"

			if created_dir and os.path.isdir(created_dir):
				try:
					os.replace(created_dir, final_dir)
				except Exception:
					# Fallback to shutil.move for cross-device moves
					import shutil
					shutil.move(created_dir, final_dir)
				print(f"Tiles generated in: {final_dir}")
			else:
				print(
					"Tiles generated but output folder not detected; looked for one of: ",
					", ".join(candidates),
				)
		except Exception as e:
			print("Failed to generate tiles:", e)
		finally:
			try:
				w.show_done_banner("Image processing done", 3000)
			except Exception:
				pass

	try:
		w.generate_tiles.clicked.connect(on_generate_tiles_clicked)
	except Exception:
		pass
	# Reset button clears the in-memory buffer and resets the viewer
	def _reset():
		if hasattr(w, "loaded_image_bytes"):
			delattr(w, "loaded_image_bytes")
		if hasattr(w, "loaded_image_vips"):
			delattr(w, "loaded_image_vips")
		if hasattr(w, "loaded_image_path"):
			delattr(w, "loaded_image_path")
		if hasattr(w, "square_buffer"):
			delattr(w, "square_buffer")
		if hasattr(w, "output_image"):
			delattr(w, "output_image")
		if hasattr(w, "output_buffer"):
			delattr(w, "output_buffer")
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