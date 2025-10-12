import os
import sys
vipshome = 'libvips\\bin'
os.environ['PATH'] = vipshome + ';' + os.environ['PATH']
import pyvips


# ONLY ADD CODE BELOW THIS COMMENT
# Raise Qt image I/O allocation cap BEFORE importing any PyQt6 modules
os.environ["QT_IMAGEIO_MAXALLOC"] = str(2 * 1024 * 1024 * 1024)  # 2 GiB

from typing import List, Optional
from pathlib import Path
import json
from PyQt6.QtWidgets import QApplication, QFileDialog
from PyQt6.QtGui import QPixmap, QImageReader
from PyQt6.QtCore import QSize

import app_ui
try:
	# Raise reader-level allocation cap to 2 GiB as well
	QImageReader.setAllocationLimit(2048)  # in megabytes
except Exception:
	pass



def load_zoom_levels_table() -> List[dict]:
	"""Load table of zoom levels from zoom_levels.json adjacent to this file.

	Returns list of dicts: {"name": str, "size": int} where size is max(width, height).
	"""
	here = Path(__file__).resolve().parent
	json_path = here / "zoom_levels.json"
	try:
		with open(json_path, "r", encoding="utf-8") as f:
			data = json.load(f)
		levels = data.get("levels") or []
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
			raise ValueError("no valid levels in JSON")
		return table
	except Exception as e:
		print("Failed to load zoom_levels.json, using defaults:", e)
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
		composite = compose_centered(square, src_img)
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
	# Record path and decode with pyvips directly from file (streaming-friendly)
	setattr(window, "loaded_image_path", path)
	try:
		img = pyvips.Image.new_from_file(path, access="sequential")
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
	if fmt == "png":
		# Map quality to PNG compression (inverse relation)
		comp = int(round((100 - quality) * 9 / 99))
		comp = max(0, min(9, comp))
		rgba = ensure_rgba(img)
		return rgba.pngsave_buffer(compression=comp)
	if fmt == "webp":
		rgba = ensure_rgba(img)
		return rgba.webpsave_buffer(Q=quality)
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
		return base.jpegsave_buffer(Q=quality)
	# default png
	rgba = ensure_rgba(img)
	return rgba.pngsave_buffer()


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
	if fmt == "png":
		comp = int(round((100 - quality) * 9 / 99))
		comp = max(0, min(9, comp))
		rgba = ensure_rgba(img)
		rgba.pngsave(path, compression=comp)
		return
	if fmt == "webp":
		rgba = ensure_rgba(img)
		rgba.webpsave(path, Q=quality)
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
		base.jpegsave(path, Q=quality)
		return
	# default png
	rgba = ensure_rgba(img)
	rgba.pngsave(path)


def main():
	app = QApplication(sys.argv)
	# apply the same stylesheet as the UI file
	app.setStyleSheet(app_ui.QSS_TEMPLATE)

	w = app_ui.MainWindow()

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

	# Hook Generate Image button: build output_buffer in selected format/quality and save
	def on_generate_image_clicked():
		output_img = getattr(w, "output_image", None)
		if output_img is None:
			print("No output image available. Load an image and select a zoom level.")
			return
		requested_fmt = get_selected_file_type(w)
		quality = get_selected_quality(w)
		# Ask where to save first (so we can stream directly to disk)
		filter_map = {
			"png": "PNG Image (*.png)",
			"jpg": "JPEG Image (*.jpg *.jpeg)",
			"webp": "WebP Image (*.webp)",
		}
		# Build default filename from input with _transparebtBG suffix
		src_path = getattr(w, "loaded_image_path", None)
		if src_path:
			base = os.path.splitext(os.path.basename(src_path))[0]
			initial_dir = os.path.dirname(src_path) or os.path.expanduser("~")
			initial_name = f"{base}_transparentBG.{('jpg' if requested_fmt == 'jpg' else requested_fmt)}"
			initial_path = os.path.join(initial_dir, initial_name)
		else:
			initial_path = os.path.join(os.path.expanduser("~"), f"output.{('jpg' if requested_fmt == 'jpg' else requested_fmt)}")
		selected_filter = filter_map.get(requested_fmt, "All Files (*)")
		fname, _ = QFileDialog.getSaveFileName(
			None,
			"Save Image",
			initial_path,
			";;".join(filter_map.values()) + ";;All Files (*)",
			selected_filter,
		)
		if fname:
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
			except Exception as e:
				print("Failed to save image:", e)

	w.generate_image.clicked.connect(on_generate_image_clicked)
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