import os
import sys
import json
import subprocess
import platform
import re
from pathlib import Path

# ============================================================
#  常量与配置
# ============================================================

IMAGE_EXTS = ['.tga', '.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.dds']

def get_base_dir():
    """获取程序运行目录，兼容打包后的 exe"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent

PRESET_FILE = get_base_dir() / "channel_presets.json"

# 内置预设
DEFAULT_PRESETS_JSON = r'''{
    "PBR_Standard": {
        "texture_tiling": 1,
        "albedo": { "enabled": true, "texture": "_BC", "channel": "RGBA", "srgb": true },
        "normal": { "enabled": true, "texture": "_N", "channel": "RGBA", "srgb": false },
        "displacement": { "enabled": true, "texture": "_H", "channel": "RGBA", "srgb": false },
        "roughness": { "enabled": true, "texture": "_R", "channel": "RGBA", "srgb": false },
        "metalness": { "enabled": true, "texture": "_M", "channel": "RGBA", "srgb": false },
        "occlusion": { "enabled": true, "texture": "_AO", "channel": "RGBA", "srgb": false }
    },
    "RHAM": {
        "texture_tiling": 1,
        "albedo": { "enabled": true, "texture": "_BC", "channel": "RGBA", "srgb": true },
        "normal": { "enabled": true, "texture": "_N", "channel": "RGBA", "srgb": false },
        "displacement": { "enabled": true, "texture": "_RHAM", "channel": "G", "srgb": false },
        "roughness": { "enabled": true, "texture": "_RHAM", "channel": "R", "srgb": false },
        "metalness": { "enabled": true, "texture": "_RHAM", "channel": "A", "srgb": false },
        "occlusion": { "enabled": true, "texture": "_RHAM", "channel": "B", "srgb": false }
    }
}'''

# 通道配置：key → (显示名, 图标, 默认 sRGB)
CHANNEL_META = {
    "albedo":       ("Albedo",       "⬜", True),
    "normal":       ("Normal",       "🔵", False),
    "displacement": ("Height",       "⬆", False),
    "roughness":    ("Roughness",    "〰", False),
    "metalness":    ("Metalness",    "◈", False),
    "occlusion":    ("Occlusion",    "◉", False),
    "emissive":     ("Emissive",     "◆", True),
}

CHANNEL_ORDER = ["albedo", "normal", "displacement", "roughness", "metalness", "occlusion", "emissive"]

# 已知贴图后缀，用于 base name 推断
KNOWN_SUFFIX_PATTERN = re.compile(
    r'(_BC|_N|_H|_R|_M|_AO|_D|_ORM|_RHAM|_RMEA|_E|_BaseColor|_Normal'
    r'|_Roughness|_Metalness|_Metallic|_Displacement|_Height|_Occlusion|_Emissive)$',
    re.IGNORECASE
)


# ============================================================
#  环境检查
# ============================================================

def ensure_pyside6():
    try:
        from PySide6 import QtWidgets, QtGui, QtCore
        return QtWidgets, QtGui, QtCore
    except ImportError:
        print("[tbmat] PySide6 未安装，正在安装...")
        flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "PySide6", "--quiet"],
            check=True, creationflags=flags
        )
        from PySide6 import QtWidgets, QtGui, QtCore
        return QtWidgets, QtGui, QtCore


QtWidgets, QtGui, QtCore = ensure_pyside6()


# ============================================================
#  核心逻辑
# ============================================================

def load_presets() -> dict:
    if PRESET_FILE.exists():
        try:
            with open(PRESET_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return json.loads(DEFAULT_PRESETS_JSON)


def save_presets(presets: dict):
    try:
        with open(PRESET_FILE, "w", encoding="utf-8") as f:
            json.dump(presets, f, indent=4, ensure_ascii=False)
    except OSError as e:
        print(f"[tbmat] 预设保存失败: {e}")


def infer_base_name(file_path) -> str:
    name = Path(file_path).stem
    return KNOWN_SUFFIX_PATTERN.sub("", name)


def find_texture_file(directory: Path, base_name: str, suffix: str) -> str | None:
    for ext in IMAGE_EXTS:
        candidate = directory / f"{base_name}{suffix}{ext}"
        if candidate.exists():
            return candidate.as_posix()
    return None


def channel_idx(ch: str) -> int:
    return {"RGBA": 0, "R": 0, "G": 1, "B": 2, "A": 3}.get(ch, 0)


# ============================================================
#  tbmat 构建
# ============================================================

def build_tbmat(directory: Path, base_name: str, config: dict) -> str:
    parts = []

    def tex(key):
        return find_texture_file(directory, base_name, config[key]["texture"]) or ""

    def srgb(key):
        return 1 if config[key]["srgb"] else 0

    def ch(key):
        return channel_idx(config[key]["channel"])

    def enabled(key):
        return config.get(key, {}).get("enabled", False)

    # Displacement
    if enabled("displacement"):
        t = tex("displacement")
        parts.append(f"""@Sub SRDisplacement = SRDisplacementHeight
    material_layer_blending_mode = 1
    Displacement Map = @Tex file "{t}" srgb {srgb("displacement")} filter 1 mip 0 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@TexSet
@Tex file "{t}" srgb {srgb("displacement")} filter 1 mip 0 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@EndTexSet
    Channel = {ch("displacement")}
    Scale = 0.01
    Scale Center = 0.5
@End""")

    # Normal
    if enabled("normal"):
        t = tex("normal")
        parts.append(f"""@Sub SRSurface = SRSurfaceNormalMap
    material_layer_blending_mode = 1
    Normal Map = @Tex file "{t}" srgb {srgb("normal")} filter 1 mip 1 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@TexSet
@Tex file "{t}" srgb {srgb("normal")} filter 1 mip 1 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@EndTexSet
    Flip Y = 1
@End""")

    # Albedo
    if enabled("albedo"):
        t = tex("albedo")
        parts.append(f"""@Sub SRAlbedo = SRAlbedoMap
    material_layer_blending_mode = 1
    Albedo Map = @Tex file "{t}" srgb {srgb("albedo")} filter 1 mip 1 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@TexSet
@Tex file "{t}" srgb {srgb("albedo")} filter 1 mip 1 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@EndTexSet
@End""")

    parts.append("@Sub SRDiffusion = SRDiffusionLambertian\n    material_layer_blending_mode = 1\n@End")
    parts.append("@Sub SRReflection = SRReflectionGGX\n    material_layer_blending_mode = 1\n@End")

    # Roughness
    if enabled("roughness"):
        t = tex("roughness")
        parts.append(f"""@Sub SRMicrosurface = SRMicrosurfaceRoughnessMap
    Roughness Map = @Tex file "{t}" srgb {srgb("roughness")} filter 1 mip 0 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@TexSet
@Tex file "{t}" srgb {srgb("roughness")} filter 1 mip 0 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@EndTexSet
    Channel = {ch("roughness")}
    Roughness = 1
@End""")

    # Metalness
    if enabled("metalness"):
        t = tex("metalness")
        parts.append(f"""@Sub SRReflectivity = SRReflectivityMetalnessMap
    Metalness Map = @Tex file "{t}" srgb {srgb("metalness")} filter 1 mip 0 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@TexSet
@Tex file "{t}" srgb {srgb("metalness")} filter 1 mip 0 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@EndTexSet
    Channel = {ch("metalness")}
    Metalness = 1
@End""")

    # Occlusion
    if enabled("occlusion"):
        t = tex("occlusion")
        parts.append(f"""@Sub SROcclusion = SROcclusionMap
    Occlusion Map = @Tex file "{t}" srgb {srgb("occlusion")} filter 1 mip 0 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@TexSet
@Tex file "{t}" srgb {srgb("occlusion")} filter 1 mip 0 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@EndTexSet
    Channel;occlusion = {ch("occlusion")}
@End""")

    # Emissive
    if enabled("emissive"):
        t = tex("emissive")
        parts.append(f"""@Sub SREmission = SREmissionMap
    material_layer_blending_mode = 1
    Emission Map = @Tex file "{t}" srgb {srgb("emissive")} filter 1 mip 1 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@TexSet
@Tex file "{t}" srgb {srgb("emissive")} filter 1 mip 1 aniso 4 wrap 1 visible 1 udim 0 @EndTex
@EndTexSet
    Intensity = 1
@End""")

    # Tiling & footer
    tiling = config.get("texture_tiling", 1)
    parts.append(f"""@Sub SRTexture = SRTextureUv
    Texture Tiling = {tiling}
@End
@Sub SRMerge = SRMerge
    material_layer_blending_mode = 1
@End
@LayerCompositor None
@End""")

    return "\n".join(parts)


# ============================================================
#  UI — ChannelRow（横向紧凑单行布局）
# ============================================================

class ChannelRow(QtWidgets.QWidget):
    changed = QtCore.Signal()

    # 各列固定宽度
    COL_TOGGLE  = 20
    COL_LABEL   = 100
    COL_STATUS  = 14
    COL_SUFFIX  = 72
    COL_CHANNEL = 64
    COL_SRGB    = 52

    def __init__(self, ch_key: str, label: str, icon: str, data: dict, parent=None):
        super().__init__(parent)
        self.ch_key = ch_key
        self._build(label, icon, data)

    def _build(self, label: str, icon: str, data: dict):
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)

        # ── 启用开关（无文字）
        self.enable_cb = QtWidgets.QCheckBox()
        self.enable_cb.setChecked(data.get("enabled", True))
        self.enable_cb.setFixedWidth(self.COL_TOGGLE)
        self.enable_cb.toggled.connect(self._on_toggle)
        self.enable_cb.toggled.connect(lambda: self.changed.emit())

        # ── 图标 + 名称
        lbl_widget = QtWidgets.QLabel(f"{icon}  {label}")
        lbl_widget.setFixedWidth(self.COL_LABEL)
        lbl_widget.setObjectName("ChannelLabel")

        # ── 状态灯
        self.status_dot = QtWidgets.QLabel("●")
        self.status_dot.setFixedWidth(self.COL_STATUS)
        self.status_dot.setAlignment(QtCore.Qt.AlignCenter)
        self._set_dot("idle")

        # ── 分隔线
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.VLine)
        sep.setObjectName("VSep")

        # ── 后缀
        suffix_lbl = QtWidgets.QLabel("后缀")
        suffix_lbl.setObjectName("FieldLabel")
        self.tex_edit = QtWidgets.QLineEdit(data.get("texture", ""))
        self.tex_edit.setFixedWidth(self.COL_SUFFIX)
        self.tex_edit.setPlaceholderText("_BC")
        self.tex_edit.textChanged.connect(lambda: self.changed.emit())

        # ── 通道
        channel_lbl = QtWidgets.QLabel("通道")
        channel_lbl.setObjectName("FieldLabel")
        self.ch_combo = QtWidgets.QComboBox()
        self.ch_combo.addItems(["RGBA", "R", "G", "B", "A"])
        self.ch_combo.setCurrentText(data.get("channel", "RGBA"))
        self.ch_combo.setFixedWidth(self.COL_CHANNEL)
        self.ch_combo.currentIndexChanged.connect(lambda: self.changed.emit())

        # ── sRGB
        self.srgb_cb = QtWidgets.QCheckBox("sRGB")
        self.srgb_cb.setChecked(data.get("srgb", False))
        self.srgb_cb.setFixedWidth(self.COL_SRGB)
        self.srgb_cb.toggled.connect(lambda: self.changed.emit())

        row.addWidget(self.enable_cb)
        row.addWidget(lbl_widget)
        row.addWidget(self.status_dot)
        row.addWidget(sep)
        row.addWidget(suffix_lbl)
        row.addWidget(self.tex_edit)
        row.addWidget(channel_lbl)
        row.addWidget(self.ch_combo)
        row.addWidget(self.srgb_cb)
        row.addStretch()

        self._on_toggle(self.enable_cb.isChecked())

    def _on_toggle(self, checked: bool):
        """启用/禁用时整行变暗"""
        opacity = 1.0 if checked else 0.38
        effect = QtWidgets.QGraphicsOpacityEffect(self)
        effect.setOpacity(opacity)
        # 保留 checkbox 本身不变暗
        self.enable_cb.setGraphicsEffect(None)
        for w in (self.tex_edit, self.ch_combo, self.srgb_cb):
            w.setEnabled(checked)
        # 整体 opacity 用 setEnabled 对子控件不够精确，用 effect 作用于父容器外层
        # 这里简单标记 objectName 让 QSS 处理
        self.setProperty("dimmed", not checked)
        self.style().unpolish(self)
        self.style().polish(self)

    def _set_dot(self, state: str):
        colors = {"ok": "#22C55E", "missing": "#EF4444", "idle": "#334155"}
        size = "12px" if state != "idle" else "10px"
        self.status_dot.setStyleSheet(
            f"color: {colors.get(state, '#334155')}; font-size: {size};"
        )
        tips = {"ok": "贴图已找到", "missing": "贴图未找到", "idle": "未启用"}
        self.status_dot.setToolTip(tips.get(state, ""))

    def set_status(self, found: bool | None):
        if found is None:
            self._set_dot("idle")
        else:
            self._set_dot("ok" if found else "missing")

    def get_config(self) -> dict:
        return {
            "enabled":  self.enable_cb.isChecked(),
            "texture":  self.tex_edit.text(),
            "channel":  self.ch_combo.currentText(),
            "srgb":     self.srgb_cb.isChecked(),
        }


# ============================================================
#  UI — 主窗口
# ============================================================

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.presets: dict = load_presets()
        self.ch_rows: dict[str, ChannelRow] = {}
        self.current_files: list[Path] = []

        self.setWindowTitle("Marmoset tbmat Generator")
        self.setMinimumWidth(620)
        self.setAcceptDrops(True)
        self._apply_style()
        self._build_ui()
        self._apply_preset(list(self.presets.keys())[0])

    # ── 样式 ────────────────────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet("""
/* ── 全局 ── */
QMainWindow, QWidget {
    background-color: #0D1117;
    color: #C9D1D9;
    font-family: 'Consolas', 'JetBrains Mono', 'Courier New', monospace;
    font-size: 12px;
}

/* ── 标题栏区块 ── */
QLabel#AppTitle {
    color: #E6EDF3;
    font-size: 15px;
    font-weight: bold;
    letter-spacing: 2px;
}
QLabel#AppSubtitle {
    color: #484F58;
    font-size: 10px;
    letter-spacing: 1px;
}

/* ── Section 标题 ── */
QLabel#SectionTitle {
    color: #58A6FF;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 3px;
    padding: 0px 0px 4px 0px;
}

/* ── 卡片容器 ── */
QFrame#Card {
    background-color: #161B22;
    border: 1px solid #21262D;
    border-radius: 6px;
}

/* ── 通道行容器 ── */
QWidget#ChannelRowContainer {
    background-color: #0D1117;
    border-radius: 4px;
}

/* ── 通道行 dimmed 状态 ── */
ChannelRow[dimmed="true"] QLabel#ChannelLabel {
    color: #484F58;
}

/* ── 字段标签 ── */
QLabel#FieldLabel {
    color: #484F58;
    font-size: 10px;
    letter-spacing: 1px;
}

/* ── 通道名称标签 ── */
QLabel#ChannelLabel {
    color: #8B949E;
    font-size: 11px;
}

/* ── 竖分隔线 ── */
QFrame#VSep {
    color: #21262D;
    max-width: 1px;
    min-height: 20px;
}

/* ── 输入控件 ── */
QLineEdit, QComboBox, QSpinBox {
    background-color: #0D1117;
    border: 1px solid #30363D;
    border-radius: 4px;
    padding: 3px 6px;
    color: #C9D1D9;
    selection-background-color: #1F6FEB;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #1F6FEB;
}
QComboBox::drop-down {
    border: none;
    width: 18px;
}
QComboBox::down-arrow {
    width: 8px;
    height: 8px;
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8B949E;
}
QComboBox QAbstractItemView {
    background-color: #161B22;
    border: 1px solid #30363D;
    selection-background-color: #1F6FEB;
    outline: none;
}

/* ── 按钮 ── */
QPushButton {
    background-color: #21262D;
    color: #C9D1D9;
    border: 1px solid #30363D;
    border-radius: 4px;
    padding: 4px 12px;
}
QPushButton:hover {
    background-color: #30363D;
    border-color: #8B949E;
}
QPushButton:pressed {
    background-color: #0D1117;
}
QPushButton#PrimaryBtn {
    background-color: #1F6FEB;
    color: #FFFFFF;
    border: none;
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 1px;
    border-radius: 5px;
}
QPushButton#PrimaryBtn:hover {
    background-color: #388BFD;
}
QPushButton#PrimaryBtn:pressed {
    background-color: #1158C7;
}
QPushButton#DangerBtn {
    color: #F85149;
    border-color: #3D1F1E;
}
QPushButton#DangerBtn:hover {
    background-color: #3D1F1E;
    border-color: #F85149;
}

/* ── CheckBox ── */
QCheckBox {
    spacing: 6px;
    color: #8B949E;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid #30363D;
    background: #0D1117;
}
QCheckBox::indicator:checked {
    background-color: #1F6FEB;
    border-color: #1F6FEB;
    image: none;
}

/* ── 滚动条 ── */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: #0D1117;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #30363D;
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── 拖放区 ── */
QLabel#DropZone {
    color: #484F58;
    border: 1px dashed #30363D;
    border-radius: 6px;
    font-size: 11px;
}
QLabel#DropZoneActive {
    color: #8B949E;
    border: 1px solid #1F6FEB;
    border-radius: 6px;
    font-size: 11px;
}

/* ── 状态栏 ── */
QLabel#StatusBar {
    color: #484F58;
    font-size: 10px;
    padding: 2px 0px;
}
""")

    # ── UI 构建 ─────────────────────────────────────────────

    def _build_ui(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        main = QtWidgets.QVBoxLayout(root)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(12)

        main.addWidget(self._build_header())
        main.addWidget(self._build_preset_section())
        main.addWidget(self._build_drop_section())
        main.addWidget(self._build_channel_section())
        main.addWidget(self._build_footer())

    def _section_title(self, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("SectionTitle")
        return lbl

    def _card(self) -> QtWidgets.QFrame:
        f = QtWidgets.QFrame()
        f.setObjectName("Card")
        return f

    def _build_header(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 4)

        left = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("TBMAT GENERATOR")
        title.setObjectName("AppTitle")
        sub = QtWidgets.QLabel("MARMOSET TOOLBAG  ·  MATERIAL FILE BUILDER")
        sub.setObjectName("AppSubtitle")
        left.addWidget(title)
        left.addWidget(sub)

        layout.addLayout(left)
        layout.addStretch()
        return w

    def _build_preset_section(self) -> QtWidgets.QFrame:
        card = self._card()
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(self._section_title("PRESET"))

        row = QtWidgets.QHBoxLayout()
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.addItems(self.presets.keys())
        self.preset_combo.currentTextChanged.connect(self._apply_preset)

        save_btn = QtWidgets.QPushButton("另存为…")
        save_btn.clicked.connect(self._save_preset)

        del_btn = QtWidgets.QPushButton("删除")
        del_btn.setObjectName("DangerBtn")
        del_btn.clicked.connect(self._delete_preset)

        row.addWidget(self.preset_combo, 1)
        row.addWidget(save_btn)
        row.addWidget(del_btn)
        layout.addLayout(row)
        return card

    def _build_drop_section(self) -> QtWidgets.QFrame:
        card = self._card()
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(self._section_title("INPUT"))

        self.drop_label = QtWidgets.QLabel(
            "将贴图文件拖入此处\n"
            "支持格式：TGA  PNG  JPG  BMP  TIF  DDS"
        )
        self.drop_label.setObjectName("DropZone")
        self.drop_label.setAlignment(QtCore.Qt.AlignCenter)
        self.drop_label.setFixedHeight(64)
        layout.addWidget(self.drop_label)

        # 文件信息行
        info_row = QtWidgets.QHBoxLayout()
        self.file_count_lbl  = QtWidgets.QLabel("—")
        self.file_base_lbl   = QtWidgets.QLabel("")
        self.file_base_lbl.setObjectName("StatusBar")
        self.file_count_lbl.setObjectName("StatusBar")
        info_row.addWidget(self.file_count_lbl)
        info_row.addWidget(self.file_base_lbl, 1)

        # Tiling
        info_row.addStretch()
        info_row.addWidget(QtWidgets.QLabel("Tiling"))
        self.tiling_spin = QtWidgets.QSpinBox()
        self.tiling_spin.setRange(1, 100)
        self.tiling_spin.setFixedWidth(52)
        info_row.addWidget(self.tiling_spin)

        layout.addLayout(info_row)
        return card

    def _build_channel_section(self) -> QtWidgets.QFrame:
        card = self._card()
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # 表头
        header_row = QtWidgets.QHBoxLayout()
        header_row.setContentsMargins(12, 0, 12, 0)
        header_row.setSpacing(10)

        def hdr(text, width=None):
            l = QtWidgets.QLabel(text)
            l.setObjectName("FieldLabel")
            if width:
                l.setFixedWidth(width)
            return l

        header_row.addWidget(hdr("", ChannelRow.COL_TOGGLE))
        header_row.addWidget(hdr("CHANNEL", ChannelRow.COL_LABEL + ChannelRow.COL_STATUS + 10))
        header_row.addSpacing(1 + 10)  # sep + spacing
        header_row.addWidget(hdr("SUFFIX", ChannelRow.COL_SUFFIX + 10 + 28))  # label + spacing + label_width
        header_row.addWidget(hdr("CH", ChannelRow.COL_CHANNEL + 10 + 20))
        header_row.addWidget(hdr("COLOR", ChannelRow.COL_SRGB))
        header_row.addStretch()
        layout.addLayout(header_row)

        # 分割线
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("color: #21262D;")
        layout.addWidget(line)

        # 通道行
        for key in CHANNEL_ORDER:
            label, icon, _ = CHANNEL_META[key]
            row = ChannelRow(key, label, icon, {})
            row.changed.connect(self._refresh_status)
            self.ch_rows[key] = row
            layout.addWidget(row)

            if key != CHANNEL_ORDER[-1]:
                sep = QtWidgets.QFrame()
                sep.setFrameShape(QtWidgets.QFrame.HLine)
                sep.setStyleSheet("color: #161B22; margin: 0px 12px;")
                layout.addWidget(sep)

        return card

    def _build_footer(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.status_lbl = QtWidgets.QLabel("就绪")
        self.status_lbl.setObjectName("StatusBar")

        self.gen_btn = QtWidgets.QPushButton("⬡  生成 .tbmat 文件")
        self.gen_btn.setObjectName("PrimaryBtn")
        self.gen_btn.setFixedHeight(42)
        self.gen_btn.clicked.connect(self._generate)

        layout.addWidget(self.status_lbl, 1)
        layout.addWidget(self.gen_btn)
        return w

    # ── 逻辑处理 ────────────────────────────────────────────

    def _apply_preset(self, name: str):
        if name not in self.presets:
            return
        cfg = self.presets[name]
        self.tiling_spin.setValue(cfg.get("texture_tiling", 1))
        for key, row in self.ch_rows.items():
            data = cfg.get(key, {})
            row.enable_cb.setChecked(data.get("enabled", False))
            row.tex_edit.setText(data.get("texture", ""))
            row.ch_combo.setCurrentText(data.get("channel", "RGBA"))
            row.srgb_cb.setChecked(data.get("srgb", False))
        self._refresh_status()

    def _save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "保存预设", "预设名称:")
        if not ok or not name.strip():
            return
        name = name.strip()
        cfg = {"texture_tiling": self.tiling_spin.value()}
        for key, row in self.ch_rows.items():
            cfg[key] = row.get_config()
        self.presets[name] = cfg
        save_presets(self.presets)
        if self.preset_combo.findText(name) == -1:
            self.preset_combo.addItem(name)
        self.preset_combo.setCurrentText(name)

    def _delete_preset(self):
        name = self.preset_combo.currentText()
        if name in DEFAULT_PRESETS:
            QtWidgets.QMessageBox.warning(self, "提示", "内置预设无法删除")
            return
        reply = QtWidgets.QMessageBox.question(
            self, "确认删除", f'确定要删除预设 "{name}" 吗？',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        del self.presets[name]
        save_presets(self.presets)
        self.preset_combo.removeItem(self.preset_combo.currentIndex())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        files = [
            Path(u.toLocalFile())
            for u in event.mimeData().urls()
            if Path(u.toLocalFile()).suffix.lower() in IMAGE_EXTS
        ]
        if not files:
            return
        self.current_files = files
        base = infer_base_name(files[0])
        self.file_count_lbl.setText(f"{len(files)} 个文件")
        self.file_base_lbl.setText(f"base: {base}   @ {files[0].parent}")
        self.drop_label.setObjectName("DropZoneActive")
        self.drop_label.setText(
            "\n".join(f.name for f in files[:3])
            + (f"\n…及另 {len(files)-3} 个" if len(files) > 3 else "")
        )
        self.drop_label.style().unpolish(self.drop_label)
        self.drop_label.style().polish(self.drop_label)
        self._refresh_status()

    def _refresh_status(self):
        if not self.current_files:
            for row in self.ch_rows.values():
                row.set_status(None)
            return

        directory = self.current_files[0].parent
        base = infer_base_name(self.current_files[0])
        ok_count = 0

        for key, row in self.ch_rows.items():
            cfg = row.get_config()
            if not cfg["enabled"]:
                row.set_status(None)
                continue
            found = find_texture_file(directory, base, cfg["texture"])
            row.set_status(bool(found))
            if found:
                ok_count += 1

        enabled_count = sum(1 for r in self.ch_rows.values() if r.enable_cb.isChecked())
        self.status_lbl.setText(
            f"贴图检测：{ok_count}/{enabled_count} 已找到   base → {base}"
        )

    def _generate(self):
        if not self.current_files:
            QtWidgets.QMessageBox.warning(self, "警告", "请先拖入贴图文件")
            return

        config = {"texture_tiling": self.tiling_spin.value()}
        for key, row in self.ch_rows.items():
            config[key] = row.get_config()

        errors = []
        success = 0
        for fp in self.current_files:
            try:
                content = build_tbmat(fp.parent, infer_base_name(fp), config)
                out_path = fp.parent / f"{infer_base_name(fp)}.tbmat"
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content)
                success += 1
            except Exception as e:
                errors.append(f"{fp.name}：{e}")

        if errors:
            QtWidgets.QMessageBox.warning(
                self, f"完成（{success} 成功 / {len(errors)} 失败）",
                "\n".join(errors)
            )
        else:
            QtWidgets.QMessageBox.information(
                self, "完成", f"成功生成 {success} 个 .tbmat 文件"
            )
        if platform.system() == "Windows" and self.current_files:
            os.startfile(self.current_files[0].parent)


# ============================================================
#  入口
# ============================================================

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
