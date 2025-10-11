import sys
from dataclasses import dataclass, field
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QImageReader
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QGridLayout,
    QCheckBox,
    QFileDialog,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QAbstractSpinBox,
)


# ===========================
# Theme and Style (MODERN & FOCUSED THEME)
# ===========================
THEME = {
    "font": "Segoe UI",
    "bg": "#1A202C",          # Dark Slate
    "panel": "#2D3748",       # Lighter Slate
    "text": "#F7FAFC",        # Off-white
    "muted": "#A0AEC0",       # Gray for labels
    "accent": "#4299E1",      # Vibrant Blue
    "accentHover": "#63B3ED", # Lighter Blue for hover
    "accentDisabled": "#2A4365",
    "border": "#4A5568",
    "radius": 6,
    "spacing": 12,
    "padding": "10px 15px",
}

# Complete stylesheet with all the requested enhancements
QSS_TEMPLATE = f"""
/* --- Global --- */
* {{
    font-family: "{THEME['font']}";
    color: {THEME['text']};
}}

QMainWindow {{
    background-color: {THEME['bg']};
}}

/* --- Typography --- */
QLabel#title {{
    color: {THEME['text']};
    font-weight: 600;
}}
QLabel[role="muted"] {{
    color: {THEME['muted']};
}}

/* --- Panels & Frames --- */
QFrame[kind="panel"], QFrame#zoom_panel {{
    background-color: {THEME['panel']};
    border: none;
    border-radius: {THEME['radius']}px;
}}
QFrame[kind="viewer"] {{
    background-color: {THEME['panel']};
    border: 2px dashed {THEME['border']};
    border-radius: {THEME['radius']}px;
}}
QFrame#zoom_panel QLabel {{
    color: {THEME['muted']};
}}

/* --- Buttons --- */
QPushButton {{
    background-color: {THEME['accent']};
    color: white;
    font-weight: 600;
    border: none;
    border-radius: {THEME['radius']}px;
    padding: {THEME['padding']};
}}
QPushButton:hover {{
    background-color: {THEME['accentHover']};
}}
QPushButton:pressed {{
    background-color: {THEME['accent']};
}}
QPushButton:disabled {{
    background-color: {THEME['accentDisabled']};
    color: {THEME['border']};
}}

/* --- Inputs (LineEdit, SpinBox, ComboBox) --- */
QLineEdit, QSpinBox, QComboBox {{
    background-color: {THEME['bg']};
    border: 1px solid {THEME['border']};
    border-radius: {THEME['radius']}px;
    padding: 8px 10px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {THEME['accent']};
}}

/* --- ComboBox (Dropdown Menu) Styling --- */
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 25px;
    border-left-width: 1px;
    border-left-color: {THEME['border']};
    border-left-style: solid;
    border-top-right-radius: {THEME['radius']}px;
    border-bottom-right-radius: {THEME['radius']}px;
}}
QComboBox::down-arrow {{
    image: url(./down_arrow.png); /* For a better arrow, provide a custom icon */
}}
QComboBox QAbstractItemView {{
    background-color: {THEME['panel']};
    border: 1px solid {THEME['border']};
    border-radius: {THEME['radius']}px;
    selection-background-color: {THEME['accent']};
    selection-color: white;
    outline: 0px;
}}

/* --- ScrollBar --- */
QScrollBar:vertical {{
    border: none;
    background: {THEME['bg']};
    width: 10px;
    margin: 0px 0px 0px 0px;
}}
QScrollBar::handle:vertical {{
    background: {THEME['border']};
    min-height: 20px;
    border-radius: 5px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

/* --- Tooltip --- */
QToolTip {{
    color: {THEME['text']};
    background-color: {THEME['panel']};
    border: 1px solid {THEME['border']};
    border-radius: {THEME['radius']}px;
    padding: 5px;
}}
"""


# ===========================
# Helper widgets
# ===========================
class ValueComboBox(QComboBox):
    """QComboBox with a .value property for convenience.

    .value returns currentText() by default. If items were added with userData,
    .value returns currentData() when available.
    """

    @property
    def value(self) -> str:
        data = self.currentData()
        return data if data is not None else self.currentText()

    def set_items(self, items: List[str]):
        """Replace items quickly. Accepts a list of strings.
        Keep this simple to make editing easy.
        """
        self.clear()
        for text in items:
            self.addItem(text, text)


class IntSpinBox(QSpinBox):
    """QSpinBox exposing a .value property to match ValueComboBox semantics."""

    @property
    def value(self) -> int:
        # call the underlying QSpinBox.value() method
        return super().value()


class ZoomLevelWidget(QWidget):
    """Composite widget for a zoom level definition.

    Contains:
    - QLineEdit named 'zoom_level_name'
    - QSpinBox named 'square_size' (integer only), labeled "square size"
    UI only: no behavior, just fields.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("zoom_level_widget")

        # Layout and container frame to style as a panel
        container = QFrame(self)
        container.setObjectName("zoom_panel")
        container.setFrameShape(QFrame.Shape.NoFrame)

        form = QFormLayout(container)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(15, 15, 15, 15)
        form.setSpacing(10)

        # Text input: zoom_level_name
        self.zoom_level_name = QLineEdit(container)
        self.zoom_level_name.setObjectName("zoom_level_name")
        self.zoom_level_name.setPlaceholderText("My zoom level")
        form.addRow("Name:", self.zoom_level_name)

        # Integer input: square_size (with label "square size")
        self.square_size = QSpinBox(container)
        self.square_size.setObjectName("square_size")
        self.square_size.setRange(1, 100000)  # generous range; UI only
        self.square_size.setValue(256)
        form.addRow("Square Size:", self.square_size)

        # outer layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)


class DropImageViewer(QFrame):
    """Clickable + Drag-and-Drop image viewer (images only).

    - Click: opens a file dialog for images
    - Drag & drop: accepts only image files by extension
    - Scales loaded image to fit while preserving aspect ratio
    """

    # Signals to delegate behavior to the application layer
    openFileRequested = pyqtSignal()
    pathsDropped = pyqtSignal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("image_viewer")
        self.setProperty("kind", "viewer")
        self.setAcceptDrops(True)

        self._pixmap: Optional[QPixmap] = None
        self.selected_path: Optional[str] = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # separate QLabel for the rendered image (hidden when no image)
        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # don't scale contents automatically -- we scale the pixmap ourselves
        self._image_label.setScaledContents(False)
        self._image_label.setVisible(False)

        # placeholder label shown when no image is loaded
        self._placeholder = QLabel("CLICK OR DROP IMAGE FILE HERE", self)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setProperty("role", "muted")
        # make placeholder more prominent: larger font and increased letter spacing
        ph_font = QFont()
        ph_font.setFamily(THEME.get("font", ph_font.family()))
        ph_font.setPointSize(14)  # larger size
        # Use AbsoluteSpacing to add more space between letters (units are pixels)
        try:
            ph_font.setLetterSpacing(QFont.LetterSpacingType.AbsoluteSpacing, 1.8)
        except Exception:
            # older Qt bindings may not support setLetterSpacing; ignore silently
            pass
        self._placeholder.setFont(ph_font)

        # image label below, placeholder on top (layout order doesn't matter too much)
        self._layout.addWidget(self._image_label)
        self._layout.addWidget(self._placeholder)

    # ---------- Helpers ----------
    def _update_view(self):
        # when no pixmap, show placeholder and hide image label
        if self._pixmap is None or self._pixmap.isNull():
            self._image_label.clear()
            self._image_label.setVisible(False)
            self._placeholder.setText("CLICK OR DROP IMAGE FILE HERE")
            self._placeholder.setVisible(True)
            self._placeholder.style().unpolish(self._placeholder)
            self._placeholder.style().polish(self._placeholder)
            return
        # Fit pixmap into available area preserving aspect ratio and show it
        avail = self.size()
        scaled = self._pixmap.scaled(
            avail, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self._image_label.setPixmap(scaled)
        self._image_label.setVisible(True)
        self._placeholder.setVisible(False)

    def set_image(self, path: str):
        pm = QPixmap(path)
        if pm.isNull():
            # Failed to load as image
            self._pixmap = None
            self.selected_path = None
            self._image_label.clear()
            self._image_label.setVisible(False)
            self._placeholder.setText("Failed to load image")
            self._placeholder.setVisible(True)
            return
        self._pixmap = pm
        self.selected_path = path
        self._update_view()

    # ---------- Qt events ----------
    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._update_view()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            # Delegate action to application layer
            self.openFileRequested.emit()
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):  # noqa: N802
        md = event.mimeData()
        if md.hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):  # noqa: N802
        md = event.mimeData()
        if md.hasUrls():
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
            if paths:
                self.pathsDropped.emit(paths)
                event.acceptProposedAction()
                return
        event.ignore()


@dataclass
class InitialData:
    """Easy-to-edit initial values for the UI controls."""

    # dropdown: zoom_levels
    zoom_levels: List[str] = field(
        default_factory=lambda: [
            "Choose zoom level",
            "Zoom level 1", "Zoom level 2", "Zoom level 3", "Zoom level 4",
            "Zoom level 5", "Zoom level 6", "Zoom level 7", "Zoom level 8",
            "Zoom level 9", "Zoom level 10"
        ]
    )

    # dropdown: file_type
    file_types: List[str] = field(default_factory=lambda: ["webp", "png", "jpg"])


class MainWindow(QMainWindow):
    """Main window UI only.

    Notes:
    - No business logic, no file dialogs, no processing. Pure widgets.
    - Exposes attributes with specific names so code can access e.g. self.zoom_levels.value.
    - Styling centralized via THEME and QSS_TEMPLATE above.
    """

    def __init__(self, initial: Optional[InitialData] = None):
        super().__init__()
        self.setWindowTitle("Tile Cutter")
        initial = initial or InitialData()

        # Central widget with a horizontal split: left = viewer, right = controls
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(THEME['spacing'])

        # Header (removed for a cleaner look, title bar is enough)

        # Main area: viewer + controls side-by-side
        main_row = QHBoxLayout()
        main_row.setSpacing(THEME['spacing'])
        root.addLayout(main_row, stretch=1)

        # -------------- Image Viewer (drag & drop + click-to-open) --------------
        self.image_viewer = DropImageViewer()
        self.image_viewer.setMinimumSize(400, 300)
        main_row.addWidget(self.image_viewer, stretch=3)

        # -------------- Controls Panel --------------
        controls_panel = QFrame()
        controls_panel.setProperty("kind", "panel")
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setContentsMargins(15, 15, 15, 15)
        controls_layout.setSpacing(THEME['spacing'] + 4) # More vertical space

        # Dropdown: zoom_levels (with .value property)
        self.zoom_levels = ValueComboBox()
        self.zoom_levels.setObjectName("zoom_levels")
        self.zoom_levels.set_items(list(initial.zoom_levels))
        controls_layout.addWidget(labeled("Zoom Levels", self.zoom_levels))

        # Zoom level component (composite text + integer)
        self.zoom_level = ZoomLevelWidget()
        self.zoom_level.setObjectName("zoom_level")
        controls_layout.addWidget(self.zoom_level)

        # Dropdown: file_type (values webp, png by default; easy to change)
        self.file_type = ValueComboBox()
        self.file_type.setObjectName("file_type")
        self.file_type.set_items(list(initial.file_types))
        controls_layout.addWidget(labeled("File Type", self.file_type))

        # Layout options dropdown (left of quality input)
        self.layout_options = ValueComboBox()
        self.layout_options.setObjectName("layout_options")
        # default empty options; easy to extend later
        self.layout_options.set_items(["dz", "google", "zoomify", "iiif"])

        # Image quality input (only integer numbers). Class name: image_quality
        self.image_quality = IntSpinBox()
        self.image_quality.setObjectName("image_quality")
        self.image_quality.setRange(1, 100)
        self.image_quality.setValue(100)

        # helper label for quality
        quality_box = QWidget()
        qb_layout = QVBoxLayout(quality_box)
        qb_layout.setContentsMargins(0, 0, 0, 0)
        qb_layout.setSpacing(4)
        q_label = QLabel("Quality")
        q_label.setProperty("role", "muted")
        q_helper = QLabel("100 - best quality")
        q_helper.setProperty("role", "muted")
        q_helper.setStyleSheet("font-size: 10px; color: %s;" % THEME['muted'])
        qb_layout.addWidget(q_label)
        qb_layout.addWidget(self.image_quality)
        qb_layout.addWidget(q_helper)
        # Row: layout_options (left) + gap + quality (right)
        # We'll use stretch factors so that layout_options and quality_box
        # each take 40% of the row (combined 80%) and the middle gap takes 20%.
        row = QHBoxLayout()
        row.setSpacing(8)
        gap = QWidget()
        gap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # add widgets with stretches: left=4, gap=2, right=4 -> left+right = 80%, gap=20%
        # put a visible label above the layout_options dropdown
        labeled_layout_options = labeled("Layout Options", self.layout_options)
        # prefer expanding horizontally but keep compact vertically so inputs align
        labeled_layout_options.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        quality_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(labeled_layout_options, stretch=4, alignment=Qt.AlignmentFlag.AlignTop)
        row.addWidget(gap, stretch=2)
        row.addWidget(quality_box, stretch=4, alignment=Qt.AlignmentFlag.AlignTop)
        controls_layout.addLayout(row)

        # ---------- OPTIONAL section ----------
        opt_label = QLabel("OPTIONAL")
        opt_label.setProperty("role", "muted")
        opt_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        controls_layout.addWidget(opt_label)

        # change overlap: checkbox + integer input + helper label
        self.change_overlap = QCheckBox("Change overlap")
        self.change_overlap.setObjectName("change_overlap")
        self.change_overlap_value = IntSpinBox()
        self.change_overlap_value.setRange(0, 1000)
        self.change_overlap_value.setValue(2)
        self.change_overlap_value.setObjectName("change_overlap_value")
        overlap_helper = QLabel("default value 2")
        overlap_helper.setProperty("role", "muted")

        # place optional controls in a grid so inputs align in the same column
        opt_grid = QGridLayout()
        opt_grid.setColumnStretch(0, 1)  # checkbox column
        opt_grid.setColumnStretch(1, 0)  # input column
        opt_grid.setColumnStretch(2, 1)  # spacer
        opt_grid.setColumnStretch(3, 0)  # helper label
        row_idx = 0

        # remove spinbox buttons and set style
        try:
            self.change_overlap_value.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        except Exception:
            pass

        opt_grid.addWidget(self.change_overlap, row_idx, 0)
        opt_grid.addWidget(self.change_overlap_value, row_idx, 1)
        opt_grid.addWidget(overlap_helper, row_idx, 3)
        row_idx += 1

        # change region shrink: checkbox + dropdown + helper label
        self.change_region_shrink = QCheckBox("Change region shrink")
        self.change_region_shrink.setObjectName("change_region_shrink")
        self.change_region_shrink_mode = ValueComboBox()
        self.change_region_shrink_mode.set_items(["mode", "mean", "median", "max", "min", "nearest"])
        self.change_region_shrink_mode.setObjectName("change_region_shrink_mode")
        shrink_helper = QLabel("default shrink: mode")
        shrink_helper.setProperty("role", "muted")

        opt_grid.addWidget(self.change_region_shrink, row_idx, 0)
        opt_grid.addWidget(self.change_region_shrink_mode, row_idx, 1)
        opt_grid.addWidget(shrink_helper, row_idx, 3)
        row_idx += 1

        # skip blanks: checkbox + integer input + helper label
        self.skip_blanks = QCheckBox("Skip blanks")
        self.skip_blanks.setObjectName("skip_blanks")
        self.skip_blanks_value = IntSpinBox()
        self.skip_blanks_value.setRange(0, 1000)
        self.skip_blanks_value.setValue(5)
        self.skip_blanks_value.setObjectName("skip_blanks_value")
        skip_helper = QLabel("default value 5")
        skip_helper.setProperty("role", "muted")

        try:
            self.skip_blanks_value.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        except Exception:
            pass
        opt_grid.addWidget(self.skip_blanks, row_idx, 0)
        opt_grid.addWidget(self.skip_blanks_value, row_idx, 1)
        opt_grid.addWidget(skip_helper, row_idx, 3)
        row_idx += 1

        controls_layout.addLayout(opt_grid)

        # wire checkboxes to enable/disable their inputs
        self.change_overlap.toggled.connect(lambda v: self.change_overlap_value.setEnabled(v))
        self.change_region_shrink.toggled.connect(lambda v: self.change_region_shrink_mode.setEnabled(v))
        self.skip_blanks.toggled.connect(lambda v: self.skip_blanks_value.setEnabled(v))

        # ensure inputs follow initial checkbox state
        self.change_overlap_value.setEnabled(self.change_overlap.isChecked())
        self.change_region_shrink_mode.setEnabled(self.change_region_shrink.isChecked())
        self.skip_blanks_value.setEnabled(self.skip_blanks.isChecked())

        # Ensure image_quality is only enabled for png and webp (easy to extend)
        def _update_quality_enabled():
            ft = str(self.file_type.value).lower()
            enabled = ft in ("png", "webp")
            self.image_quality.setEnabled(enabled)
            # tooltip when disabled (exact wording requested)
            if not enabled:
                self.image_quality.setToolTip("Not avaible for lossless formats")
            else:
                self.image_quality.setToolTip("")

        # initial state
        _update_quality_enabled()
        # react to changes
        self.file_type.currentIndexChanged.connect(_update_quality_enabled)

        # Spacer to push buttons to the bottom
        controls_layout.addStretch(1)

        # Buttons (UI only)
        self.generate_image = QPushButton("Generate Image")
        self.generate_image.setObjectName("generate_image")
        self.generate_tiles = QPushButton("Generate Tiles")
        self.generate_tiles.setObjectName("generate_tiles")

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)
        buttons_row.addWidget(self.generate_image, stretch=1)

        # Reset button to clear loaded image buffer and viewer
        self.reset = QPushButton("Reset")
        self.reset.setObjectName("reset")
        buttons_row.addWidget(self.reset, stretch=1)

        buttons_row.addWidget(self.generate_tiles, stretch=1)
        controls_layout.addLayout(buttons_row)

        main_row.addWidget(controls_panel, stretch=2)


def labeled(text: str, widget: QWidget) -> QWidget:
    """Small helper to place a label above a widget (stacked)."""
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(6)
    lab = QLabel(text)
    lab.setProperty("role", "muted")
    v.addWidget(lab)
    v.addWidget(widget)
    return box


def main():
    app = QApplication(sys.argv)
    # Apply global stylesheet from THEME.
    app.setStyleSheet(QSS_TEMPLATE)

    w = MainWindow()
    w.resize(1024, 640)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()