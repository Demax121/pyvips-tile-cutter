import os
import sys
vipshome = 'libvips\\bin'
os.environ['PATH'] = vipshome + ';' + os.environ['PATH']
import pyvips


# ONLY ADD CODE BELOW THIS COMMENT
from typing import List
from PyQt6.QtWidgets import QApplication, QFileDialog
from PyQt6.QtGui import QPixmap

import app_ui


def is_image_file(path: str) -> bool:
	ext = os.path.splitext(path)[1].lower()
	return ext in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif")


def load_image_to_buffer(window: app_ui.MainWindow, path: str) -> None:
	"""Load image bytes into window.loaded_image_bytes and display in viewer.

	We keep a bytes buffer on the window for later processing and call
	the UI method to set the image for display.
	"""
	try:
		with open(path, "rb") as f:
			data = f.read()
	except Exception as e:
		print("Failed to read image file:", e)
		return

	# store on the window so other code can access
	setattr(window, "loaded_image_bytes", data)
	# display from memory: load QPixmap from bytes when possible
	try:
		pm = QPixmap()
		if pm.loadFromData(data):
			# set pixmap directly on the viewer's image label if available
			if hasattr(window.image_viewer, "_pixmap"):
				window.image_viewer._pixmap = pm
				window.image_viewer._update_view()
			else:
				window.image_viewer.set_image(path)
		else:
			# fallback to file path-based display
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


def main():
	app = QApplication(sys.argv)
	# apply the same stylesheet as the UI file
	app.setStyleSheet(app_ui.QSS_TEMPLATE)

	w = app_ui.MainWindow()

	# wire signals: click opens dialog, drop loads path(s)
	w.image_viewer.openFileRequested.connect(lambda: open_file_dialog(w))
	w.image_viewer.pathsDropped.connect(lambda paths: handle_dropped_paths(w, paths))
	# Reset button clears the in-memory buffer and resets the viewer
	def _reset():
		if hasattr(w, "loaded_image_bytes"):
			delattr(w, "loaded_image_bytes")
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