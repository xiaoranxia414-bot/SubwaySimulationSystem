from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTextEdit,
    QTabWidget, QProgressBar, QStatusBar, QFrame, QSplitter,
    QTableWidget, QTableWidgetItem, QGridLayout, QGraphicsScene,
    QGraphicsView, QGraphicsEllipseItem, QGraphicsLineItem, QDialog,
    QFormLayout, QDoubleSpinBox, QSpinBox, QMessageBox, QGraphicsTextItem,
    QScrollArea, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPointF, QRectF
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QBrush, QCursor, QIcon
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

#自动检测并设置可用中文字体（兼容 Windows / Linux / macOS）（想用来修改节点设置界面的乱码问题，但是好像没起作用）
import matplotlib.font_manager as _fm
_CHINESE_FONT_PRIORITY = [
    'SimHei', 'Microsoft YaHei', 'PingFang SC',       # Windows / macOS
    'WenQuanYi Zen Hei', 'WenQuanYi Micro Hei',        # Linux
    'Noto Sans CJK SC', 'Noto Sans SC',                 # Noto 系列
    'Source Han Sans CN', 'AR PL UMing CN',
    'DejaVu Sans',                                       # 保底（不显示中文但不乱码）
]
_available_fonts = {f.name for f in _fm.fontManager.ttflist}
_chosen_font = next((f for f in _CHINESE_FONT_PRIORITY if f in _available_fonts), 'DejaVu Sans')

plt.rcParams['font.sans-serif'] = [_chosen_font]
plt.rcParams['axes.unicode_minus'] = False

import networkx as nx
import sys
import time
from core import StationGraph, SimulationEngine, PathPlanner, AnalyticsModule


def _get_qt_chinese_font(size=9) -> "QFont":
    """返回当前系统上最优的中文字体"""
    qt_candidates = [
        'SimHei', 'Microsoft YaHei', 'PingFang SC',
        'WenQuanYi Zen Hei', 'WenQuanYi Micro Hei',
        'Noto Sans CJK SC', 'Noto Sans SC',
    ]
    from PyQt5.QtGui import QFontDatabase
    available = set(QFontDatabase().families())
    for name in qt_candidates:
        if name in available:
            return QFont(name, size)
    return QFont(size)   # 系统默认字体


##  仿真线程

class SimulationThread(QThread):
    """仿真线程（UI与仿真解耦：仿真全速运行，UI由独立QTimer刷新）"""
    finished_signal = pyqtSignal(list)

    def __init__(self, simulation, steps):
        super().__init__()
        self.simulation = simulation
        self.steps = steps
        self.running = True
        self.paused = False
        self.current_step = 0
        self.history = []          # 轨迹回放历史数据

    def _record_snapshot(self):
        """记录当前仿真状态快照（用于轨迹回放）"""
        passengers = self.simulation.simulation.get_passengers()
        densities = {}
        node_counts = {}
        for node in self.simulation.station_graph.get_graph().nodes():
            node_info = self.simulation.station_graph.get_node(node)
            if node_info:
                densities[node] = node_info.get('current_density', 0)
            node_counts[node] = sum(1 for p in passengers if p.current_node == node)
        self.history.append({
            'step': self.current_step,
            'passenger_count': len(passengers),
            'densities': densities.copy(),
            'node_counts': node_counts.copy(),
        })

    def run(self):
        for i in range(self.steps):
            if not self.running:
                break
            while self.paused:
                time.sleep(0.01)
                if not self.running:
                    break
            if not self.running:
                break

            self.simulation.run_simulation_step()
            self.current_step = i + 1
            self._record_snapshot()
            time.sleep(0.001)  # 让出时间片，避免阻塞UI线程

        self.finished_signal.emit(self.history)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.running = False
        self.paused = False


##  节点图形项

class NodeItem(QGraphicsEllipseItem):
    """节点图形项（支持拖拽时连线跟随）"""

    NODE_RADIUS = 12  # 节点半径，统一管理

    def __init__(self, node_id, node_type, x, y,
                 capacity=50, area=100.0, base_speed=1.0, floor=0, parent=None):
        r = NodeItem.NODE_RADIUS
        super().__init__(-r, -r, r * 2, r * 2, parent)
        self.node_id    = node_id
        self.node_type  = node_type
        # 储完整属性，get_graph() 导出时使用
        self.capacity   = capacity
        self.area       = area
        self.base_speed = base_speed
        self.floor      = floor
        self.setPos(x, y)
        self.setBrush(self._get_brush())
        self._apply_floor_style()

        # 关键：开启位置变化通知，itemChange 才会触发
        self.setFlag(QGraphicsEllipseItem.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsEllipseItem.ItemSendsGeometryChanges, True)

        # 节点ID标签
        self.id_text = QGraphicsTextItem(node_id, self)
        self.id_text.setPos(-r, -r - 18)
        self.id_text.setDefaultTextColor(QColor('black'))

        # 人数标签
        self.count_text = QGraphicsTextItem("0人", self)
        self.count_text.setPos(-r, r + 2)
        self.count_text.setDefaultTextColor(QColor('#333333'))

        # 楼层标签（右下方）
        self.floor_text = QGraphicsTextItem(self._floor_label(), self)
        self.floor_text.setPos(r - 8, r - 10)
        self.floor_text.setDefaultTextColor(QColor('#555555'))
        font = QFont("Arial", 7)
        font.setBold(True)
        self.floor_text.setFont(font)

        # 拥堵高亮边框
        self._congestion_pen = QPen(QColor('red'), 3)

    # 颜色
    _COLOR_MAP = {
        'entrance':  '#27ae60',
        'exit':      '#e74c3c',
        'security':  '#f39c12',
        'ticket':    '#2980b9',
        'gate':      '#e67e22',
        'platform':  '#8e44ad',
        'corridor':  '#7f8c8d',
        'stairs':    '#795548',
        'escalator': '#f48fb1',
    }

    def _floor_label(self):
        if self.floor < 0:
            return f"B{abs(self.floor)}"
        elif self.floor > 0:
            return f"F{self.floor}"
        else:
            return "F0"

    def _apply_floor_style(self):
        """根据楼层设置边框样式"""
        if self.floor < 0:
            # 地下层：蓝色虚线
            self._base_pen = QPen(QColor('#2980b9'), 2, Qt.DashLine)
        elif self.floor == 0:
            # 地面层：黑色实线
            self._base_pen = QPen(QColor('black'), 2, Qt.SolidLine)
        elif self.floor == 1:
            # 站厅层：橙色实线
            self._base_pen = QPen(QColor('#e67e22'), 2, Qt.SolidLine)
        else:
            # 更高层：紫色实线
            self._base_pen = QPen(QColor('#8e44ad'), 2, Qt.SolidLine)
        self.setPen(self._base_pen)

    def _get_brush(self):
        color = self._COLOR_MAP.get(self.node_type, '#ffffff')
        return QBrush(QColor(color))

    #拥堵渐变
    def update_congestion(self, congestion):
        """congestion: 0~1 浮点，越大越红"""
        base = QColor(self._COLOR_MAP.get(self.node_type, '#ffffff'))
        r = min(255, base.red()   + int(congestion * 80))
        g = max(0,   base.green() - int(congestion * 80))
        b = max(0,   base.blue()  - int(congestion * 80))
        self.setBrush(QBrush(QColor(r, g, b)))
        if congestion > 0.6:
            self.setPen(self._congestion_pen)
        else:
            self.setPen(self._base_pen)

    # 乘客人数
    def update_passenger_count(self, count):
        self.count_text.setPlainText(f"{count}人")

    # 拖拽时连线跟随的核心逻辑
    def itemChange(self, change, value):
        # 先调用 super() 让位置真正更新，再通知关联的边
        result = super().itemChange(change, value)
        if change == QGraphicsEllipseItem.ItemPositionHasChanged:
            if self.scene():
                for item in self.scene().items():
                    if isinstance(item, EdgeItem):
                        if item.from_node is self or item.to_node is self:
                            item.update_position()
        return result


##  边图形项

class EdgeItem(QGraphicsLineItem):
    """边图形项（支持动态更新位置）"""

    def __init__(self, from_node, to_node, parent=None):
        super().__init__(parent)
        self.from_node = from_node
        self.to_node = to_node
        self._default_pen = QPen(QColor('#2c3e50'), 4)
        self.setPen(self._default_pen)
        # 开启可选中，才能被 scene.selectedItems() 捕获到
        self.setFlag(QGraphicsLineItem.ItemIsSelectable, True)
        # 确保边始终在节点下方渲染
        self.setZValue(-1)
        self.update_position()

    def itemChange(self, change, value):
        if change == QGraphicsLineItem.ItemSelectedHasChanged:
            if value:
                self.setPen(QPen(QColor('#e74c3c'), 4))   # 选中：红色，粗细相同
            else:
                self.setPen(self._default_pen)             # 取消：恢复默认
        return super().itemChange(change, value)

    def update_position(self):
        """用 scenePos() 获取全局坐标，避免父子坐标系混淆"""
        if self.from_node and self.to_node:
            fp = self.from_node.scenePos()
            tp = self.to_node.scenePos()
            self.setLine(fp.x(), fp.y(), tp.x(), tp.y())

    def update_congestion(self, congestion_factor):
        """根据拥堵系数更新线条颜色和粗细"""
        width = max(2, min(8, int(congestion_factor * 2)))
        ratio = min(1.0, (congestion_factor - 1.0) / 2.0)
        r = int(44  + ratio * (231 - 44))
        g = int(62  + ratio * (76  - 62))
        b = int(80  - ratio * 80)
        self.setPen(QPen(QColor(r, g, b), width))


##  节点属性对话框

class NodeDialog(QDialog):
    """节点属性弹窗"""

    NODE_TYPES = ['entrance', 'exit', 'security', 'ticket',
                  'gate', 'platform', 'corridor', 'stairs', 'escalator']

    def __init__(self, parent=None, node_data=None, existing_ids=None):
        """
        Args:
            existing_ids: 已存在的节点ID集合，用于重名校验
        """
        super().__init__(parent)
        self.existing_ids = existing_ids or set()
        self._original_id = node_data.get('id', '') if node_data else ''
        self.setWindowTitle("节点属性")
        self.setFixedSize(340, 340)

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # 这里是想解决Windows 上 QSpinBox/QDoubleSpinBox 数字乱码问题：
        #    对话框里所有控件单独设置一个保证包含数字字形的字体。
        _num_font  = QFont("Arial", 10)          # 数字控件用 Arial
        _text_font = _get_qt_chinese_font(10)    # 文字控件用中文字体

        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignRight)
        layout.setSpacing(10)

        # 节点ID
        self.id_edit = QLineEdit()
        self.id_edit.setFont(_text_font)
        layout.addRow("节点 ID:", self.id_edit)

        # 节点类型
        self.type_combo = QComboBox()
        self.type_combo.setFont(_text_font)
        self.type_combo.addItems(self.NODE_TYPES)
        layout.addRow("节点类型:", self.type_combo)

        # 楼层
        self.floor_spin = QSpinBox()
        self.floor_spin.setFont(_num_font)
        self.floor_spin.setRange(-5, 10)
        self.floor_spin.setValue(0)
        self.floor_spin.setPrefix("F")
        layout.addRow("楼层:", self.floor_spin)

        # 容量
        self.capacity_spin = QSpinBox()
        self.capacity_spin.setFont(_num_font)
        self.capacity_spin.setRange(1, 1000)
        self.capacity_spin.setValue(50)
        layout.addRow("容量 (人):", self.capacity_spin)

        # 面积
        self.area_spin = QDoubleSpinBox()
        self.area_spin.setFont(_num_font)
        self.area_spin.setRange(10.0, 10000.0)
        self.area_spin.setDecimals(1)
        self.area_spin.setSingleStep(10.0)
        self.area_spin.setValue(100.0)
        layout.addRow("面积 (m2):", self.area_spin)

        # 基础速度
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setFont(_num_font)
        self.speed_spin.setRange(0.1, 3.0)
        self.speed_spin.setDecimals(2)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(1.0)
        layout.addRow("速度 (m/s):", self.speed_spin)

        # 按钮
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("确定")
        self.ok_btn.setFont(_text_font)
        self.ok_btn.setMinimumHeight(30)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFont(_text_font)
        self.cancel_btn.setMinimumHeight(30)
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addRow(btn_layout)

        self.ok_btn.clicked.connect(self._on_accept)
        self.cancel_btn.clicked.connect(self.reject)

        # 填充已有数据
        if node_data:
            self.id_edit.setText(node_data.get('id', ''))
            self.type_combo.setCurrentText(node_data.get('type', 'entrance'))
            self.capacity_spin.setValue(node_data.get('capacity', 50))
            self.area_spin.setValue(node_data.get('area', 100.0))
            self.speed_spin.setValue(node_data.get('base_speed', 1.0))
            self.floor_spin.setValue(node_data.get('floor', 0))

    def _on_accept(self):
        """校验后接受"""
        node_id = self.id_edit.text().strip()
        if not node_id:
            QMessageBox.warning(self, "输入错误", "节点 ID 不能为空！")
            return
        # 仅在新建或修改了ID时检查重名
        if node_id != self._original_id and node_id in self.existing_ids:
            QMessageBox.warning(self, "输入错误", f"节点 ID「{node_id}」已存在，请换一个名称！")
            return
        self.accept()

    def get_data(self):
        return {
            'id':         self.id_edit.text().strip(),
            'type':       self.type_combo.currentText(),
            'floor':      self.floor_spin.value(),
            'capacity':   self.capacity_spin.value(),
            'area':       self.area_spin.value(),
            'base_speed': self.speed_spin.value(),
        }



###  拓扑图视图（主视图，含编辑功能）

##  时段流量配置对话框

class PeriodConfigDialog(QDialog):
    _LEVEL_MAP = {'高峰期': 'peak', '平常期': 'normal', '低谷期': 'trough'}

    def __init__(self, rules=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置时段流量")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        hint = QLabel(
            "为每个时段设置流量等级：\n"
            "  高峰期 — 时段中点流量升至基础的 4 倍\n"
            "  低谷期 — 时段中点流量降至基础的 0.2 倍\n"
            "  平常期 — 流量保持基础值不变\n"
            "未配置的时间段自动按平常期处理。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setSpacing(4)
        scroll.setWidget(self._rows_widget)
        layout.addWidget(scroll)

        add_btn = QPushButton("＋ 添加时段")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._row_widgets = []
        if rules:
            for r in rules:
                self._add_row(r)
        else:
            self._add_row()

    def _add_row(self, rule=None):
        row_w = QWidget()
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(0, 0, 0, 0)
        hours = [f"{h:02d}:00" for h in range(6, 25)]
        start_c = QComboBox(); start_c.addItems(hours)
        end_c   = QComboBox(); end_c.addItems(hours)
        level_c = QComboBox(); level_c.addItems(["高峰期", "平常期", "低谷期"])
        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(28)

        if rule:
            start_c.setCurrentIndex(max(0, rule['start'] - 6))
            end_c.setCurrentIndex(max(0, rule['end'] - 6))
            lvl_inv = {v: k for k, v in self._LEVEL_MAP.items()}
            level_c.setCurrentText(lvl_inv.get(rule['level'], '平常期'))

        row_l.addWidget(QLabel("起:"))
        row_l.addWidget(start_c)
        row_l.addWidget(QLabel("止:"))
        row_l.addWidget(end_c)
        row_l.addWidget(level_c)
        row_l.addWidget(del_btn)

        entry = (start_c, end_c, level_c, row_w)
        self._row_widgets.append(entry)
        self._rows_layout.addWidget(row_w)

        def _del():
            self._row_widgets.remove(entry)
            row_w.setParent(None)
        del_btn.clicked.connect(_del)

    def get_rules(self):
        rules = []
        for start_c, end_c, level_c, _ in self._row_widgets:
            s = start_c.currentIndex() + 6
            e = end_c.currentIndex() + 6
            if e > s:
                rules.append({'start': s, 'end': e,
                               'level': self._LEVEL_MAP[level_c.currentText()]})
        return rules if rules else None

    @staticmethod
    def rules_summary(rules):
        if not rules:
            return "未配置（全程平常期）"
        parts = []
        lvl_cn = {'peak': '高峰期', 'normal': '平常期', 'trough': '低谷期'}
        for r in rules:
            parts.append(f"{r['start']:02d}:00~{r['end']:02d}:00 {lvl_cn.get(r['level'], r['level'])}")
        return "  ".join(parts)


class TopologyView(QWidget):
    """
    拓扑图交互视图
    交互方式：
      普通模式：拖拽节点，连线自动跟随
      添加节点：点击工具栏按钮后进入十字光标模式，在画布任意位置单击即弹出属性框并创建节点
      添加边：依次点击两个节点即可连线，移动鼠标时有虚线预览
      删除：选中后按 Delete 键，或点击"删除"按钮
      双击节点：编辑节点属性（ID / 类型 / 容量等）
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar = QHBoxLayout()

        self.add_node_btn = QPushButton("添加节点")
        self.add_edge_btn = QPushButton("添加边")
        self.delete_btn   = QPushButton("删除选中")

        # 图例标签
        legend_label = QLabel()
        legend_label.setText(
            '<span style="color:#27ae60">■入口</span> '
            '<span style="color:#e74c3c">■出口</span> '
            '<span style="color:#f39c12">■安检</span> '
            '<span style="color:#2980b9">■售票</span> '
            '<span style="color:#e67e22">■闸机</span> '
            '<span style="color:#8e44ad">■站台</span> '
            '<span style="color:#7f8c8d">■通道</span>'
        )

        toolbar.addWidget(self.add_node_btn)
        toolbar.addWidget(self.add_edge_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addStretch()
        toolbar.addWidget(legend_label)
        main_layout.addLayout(toolbar)

        # 画布
        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QBrush(QColor('#f8f9fa')))

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing, True)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.setSceneRect(0, 0, 900, 620)
        main_layout.addWidget(self.view)

        # 状态
        self.add_node_mode = False   # 添加节点模式
        self.add_edge_mode = False
        self.start_node    = None    # 添加边时记录起点
        self.temp_edge     = None    # 预览虚线

        # 数据映射
        self.node_items: dict[str, NodeItem] = {}
        self.edge_items: dict[tuple, EdgeItem] = {}

        #信号连接
        self.add_node_btn.clicked.connect(self.toggle_add_node_mode)
        self.add_edge_btn.clicked.connect(self.toggle_add_edge_mode)
        self.delete_btn.clicked.connect(self.delete_selected)

        # 覆盖视图的鼠标事件
        self.view.mousePressEvent      = self._mouse_press
        self.view.mouseMoveEvent       = self._mouse_move
        self.view.mouseReleaseEvent    = self._mouse_release
        self.view.mouseDoubleClickEvent = self._mouse_double_click
        # Delete 键删除选中项
        self.view.keyPressEvent        = self._key_press

        # 加载默认拓扑
        self._load_default_topology()

    ##  模式切换

    def toggle_add_node_mode(self):

        if self.add_edge_mode:
            self._exit_add_edge_mode()

        self.add_node_mode = not self.add_node_mode
        if self.add_node_mode:
            self.add_node_btn.setText("取消添加节点")
            self.add_node_btn.setStyleSheet("background-color: #f39c12; color: white;")
            self.view.setCursor(Qt.CrossCursor)
        else:
            self.add_node_btn.setText("添加节点")
            self.add_node_btn.setStyleSheet("")
            self.view.setCursor(Qt.ArrowCursor)

    def toggle_add_edge_mode(self):
        """切换添加边模式"""
        # 先关闭添加节点模式
        if self.add_node_mode:
            self.toggle_add_node_mode()

        self.add_edge_mode = not self.add_edge_mode
        if self.add_edge_mode:
            self.add_edge_btn.setText("取消添加边")
            self.add_edge_btn.setStyleSheet("background-color: #2980b9; color: white;")
            self.view.setCursor(Qt.PointingHandCursor)
        else:
            self._exit_add_edge_mode()

    def _exit_add_edge_mode(self):
        self.add_edge_mode = False
        self.start_node = None
        self.add_edge_btn.setText("添加边")
        self.add_edge_btn.setStyleSheet("")
        self.view.setCursor(Qt.ArrowCursor)
        if self.temp_edge:
            self.scene.removeItem(self.temp_edge)
            self.temp_edge = None


    #  添加 / 删除节点和边
    def _create_node_at(self, scene_x, scene_y):
        """在指定场景坐标创建节点（弹出属性框）"""
        dialog = NodeDialog(self, existing_ids=set(self.node_items.keys()))
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            node_id = data['id']
            if node_id:
                item = NodeItem(node_id, data['type'], scene_x, scene_y,
                                capacity=data['capacity'],
                                area=data['area'],
                                base_speed=data['base_speed'],
                                floor=data.get('floor', 0))
                self.scene.addItem(item)
                self.node_items[node_id] = item

    def delete_selected(self):
        """删除当前选中的节点或边"""
        for item in list(self.scene.selectedItems()):
            if isinstance(item, NodeItem):
                self._remove_node(item)
            elif isinstance(item, EdgeItem):
                self._remove_edge_item(item)

    def _remove_node(self, node_item: NodeItem):
        """删除节点及其所有关联边"""
        edges_to_del = [
            key for key, edge in self.edge_items.items()
            if edge.from_node is node_item or edge.to_node is node_item
        ]
        for key in edges_to_del:
            self.scene.removeItem(self.edge_items.pop(key))

        del self.node_items[node_item.node_id]
        self.scene.removeItem(node_item)

    def _remove_edge_item(self, edge_item: EdgeItem):
        key_to_del = None
        for key, item in self.edge_items.items():
            if item is edge_item:
                key_to_del = key
                break
        if key_to_del:
            del self.edge_items[key_to_del]
        self.scene.removeItem(edge_item)

    #  鼠标事件
    def _mouse_press(self, event):
        scene_pos = self.view.mapToScene(event.pos())

        #添加节点模式
        if self.add_node_mode:
            self._create_node_at(scene_pos.x(), scene_pos.y())
            # 单次添加后自动退出模式（如需连续添加，可注释下行）
            self.toggle_add_node_mode()
            return

        #添加边模式
        if self.add_edge_mode:
            item = self.view.itemAt(event.pos())
            # 点到了子项（文字标签）时，向上找父节点
            while item and not isinstance(item, NodeItem):
                item = item.parentItem()

            if isinstance(item, NodeItem):
                if self.start_node is None:
                    # 记录起点，高亮提示
                    self.start_node = item
                    item.setPen(QPen(QColor('#e74c3c'), 3))
                else:
                    # 确定终点，创建边
                    if self.start_node is not item:
                        key = (self.start_node.node_id, item.node_id)
                        if key not in self.edge_items:
                            edge = EdgeItem(self.start_node, item)
                            self.scene.addItem(edge)
                            self.edge_items[key] = edge
                    # 恢复起点外观并重置
                    self.start_node.setPen(QPen(QColor('black'), 2))
                    self.start_node = None
                    if self.temp_edge:
                        self.scene.removeItem(self.temp_edge)
                        self.temp_edge = None
            return

        # 普通模式
        QGraphicsView.mousePressEvent(self.view, event)

    def _mouse_move(self, event):
        # 添加边模式：绘制虚线预览
        if self.add_edge_mode and self.start_node:
            scene_pos = self.view.mapToScene(event.pos())
            fp = self.start_node.scenePos()
            if self.temp_edge:
                self.scene.removeItem(self.temp_edge)
            self.temp_edge = QGraphicsLineItem(fp.x(), fp.y(), scene_pos.x(), scene_pos.y())
            self.temp_edge.setPen(QPen(QColor('#95a5a6'), 2, Qt.DashLine))
            self.temp_edge.setZValue(-0.5)
            self.scene.addItem(self.temp_edge)
            return

        QGraphicsView.mouseMoveEvent(self.view, event)

    def _mouse_release(self, event):
        QGraphicsView.mouseReleaseEvent(self.view, event)

    def _key_press(self, event):
        """Delete / Backspace 键删除选中的节点或边"""
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
        else:
            QGraphicsView.keyPressEvent(self.view, event)

    def _mouse_double_click(self, event):
        #双击节点可 编辑属性；双击空白可快速添加节点
        item = self.view.itemAt(event.pos())
        while item and not isinstance(item, NodeItem):
            item = item.parentItem()

        if isinstance(item, NodeItem):
            self._edit_node(item)
        else:
            scene_pos = self.view.mapToScene(event.pos())
            self._create_node_at(scene_pos.x(), scene_pos.y())


    ##  编辑节点属性

    def _edit_node(self, item: NodeItem):
        existing = set(self.node_items.keys())
        node_data = {
            'id':         item.node_id,
            'type':       item.node_type,
            'floor':      item.floor,
            'capacity':   item.capacity,
            'area':       item.area,
            'base_speed': item.base_speed,
        }
        dialog = NodeDialog(self, node_data, existing_ids=existing)
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.get_data()
            new_id   = new_data['id']
            new_type = new_data['type']
            new_floor = new_data.get('floor', 0)

            item.capacity   = new_data['capacity']
            item.area       = new_data['area']
            item.base_speed = new_data['base_speed']

            # 更新楼层（如果变更）
            if new_floor != item.floor:
                item.floor = new_floor
                item._apply_floor_style()
                item.floor_text.setPlainText(item._floor_label())

            # 更新ID（如果变更）
            if new_id != item.node_id:
                new_edges = {}
                for (f, t), edge in self.edge_items.items():
                    nf = new_id if f == item.node_id else f
                    nt = new_id if t == item.node_id else t
                    new_edges[(nf, nt)] = edge
                self.edge_items = new_edges
                del self.node_items[item.node_id]
                item.node_id = new_id
                item.id_text.setPlainText(new_id)
                self.node_items[new_id] = item

            # 更新类型和颜色
            if new_type != item.node_type:
                item.node_type = new_type
                item.setBrush(item._get_brush())


    ##  仿真数据更新
    def update_view(self, graph, passengers):
        """仿真运行中刷新拓扑图（保留当前节点位置）"""
        # 只更新乘客人数标签，不重建整个图
        node_counts = {}
        for p in passengers:
            node_counts[p.current_node] = node_counts.get(p.current_node, 0) + 1
        for node_id, item in self.node_items.items():
            item.update_passenger_count(node_counts.get(node_id, 0))

    def update_congestion(self, congestion_data: dict):
        """根据密度数据更新节点拥堵色"""
        max_val = max(congestion_data.values()) if congestion_data else 1.0
        max_val = max(max_val, 0.001)
        for node_id, val in congestion_data.items():
            if node_id in self.node_items:
                self.node_items[node_id].update_congestion(val / max_val)

        for (f, t), edge_item in self.edge_items.items():
            # 取两端节点密度均值作为边的拥堵参考
            cf = (congestion_data.get(f, 0) + congestion_data.get(t, 0)) / (2 * max_val + 1e-6)
            edge_item.update_congestion(1.0 + cf * 2)

    def reset(self):
        """重置画布，恢复默认拓扑"""
        self.scene.clear()
        self.node_items.clear()
        self.edge_items.clear()
        self._load_default_topology()

    ##  导出 StationGraph 供仿真使用
    def get_graph(self) -> StationGraph:
        """将当前画布上的节点和边转换为 StationGraph（带完整属性）"""
        graph = StationGraph()
        for node_id, item in self.node_items.items():
            pos = item.scenePos()
            graph.add_node(
                node_id, item.node_type, item.capacity,
                pos.x(), pos.y(),
                floor=item.floor,
                area=item.area, base_speed=item.base_speed
            )
        for (f, t), item in self.edge_items.items():
            fp   = item.from_node.scenePos()
            tp   = item.to_node.scenePos()
            dist = ((fp.x()-tp.x())**2 + (fp.y()-tp.y())**2) ** 0.5
            graph.add_edge(f, t, max(dist, 1.0), 2, capacity=10, base_time=1.0)
        return graph


    ##  默认拓扑
    def _load_default_topology(self):
        """加载默认的中型站拓扑（2条线路）"""
        n = 2  # 每类节点数量

        # 坐标布局（x 按流程递进，y 按索引分布）
        layout = {
            'entrance':  (60,  80),
            'ticket':    (180, 80),
            'security':  (300, 80),
            'gate':      (420, 80),
            'corridor':  (520, 160),  # 汇聚点
            'stairs':    (620, 80),
            'escalator': (620, 160),
            'platform':  (760, 80),
            'exit':      (880, 80),
        }
        y_step = 120

        def add(nid, ntype, x, y, floor=0):
            item = NodeItem(nid, ntype, x, y, floor=floor)
            self.scene.addItem(item)
            self.node_items[nid] = item

        def connect(fid, tid):
            if fid in self.node_items and tid in self.node_items:
                key = (fid, tid)
                if key not in self.edge_items:
                    edge = EdgeItem(self.node_items[fid], self.node_items[tid])
                    self.scene.addItem(edge)
                    self.edge_items[key] = edge

        for i in range(1, n + 1):
            dy = (i - 1) * y_step
            # 地面层 floor=0
            add(f'entrance{i}',  'entrance',  layout['entrance'][0],  layout['entrance'][1]  + dy, floor=0)
            add(f'exit{i}',      'exit',      layout['exit'][0],      layout['exit'][1]      + dy, floor=0)
            # 站厅层 floor=1
            add(f'ticket{i}',    'ticket',    layout['ticket'][0],    layout['ticket'][1]    + dy, floor=1)
            add(f'security{i}',  'security',  layout['security'][0],  layout['security'][1]  + dy, floor=1)
            add(f'gate{i}',      'gate',      layout['gate'][0],      layout['gate'][1]      + dy, floor=1)
            # 站台层 floor=-1
            add(f'stairs{i}',    'stairs',    layout['stairs'][0],    layout['stairs'][1]    + dy, floor=-1)
            add(f'escalator{i}', 'escalator', layout['escalator'][0], layout['escalator'][1] + dy, floor=-1)
            add(f'platform{i}',  'platform',  layout['platform'][0],  layout['platform'][1]  + dy, floor=-1)

        # 通道（汇聚点，站厅层）
        add('corridor1', 'corridor', layout['corridor'][0], layout['corridor'][1], floor=1)

        # 连接
        for i in range(1, n + 1):
            connect(f'entrance{i}',  f'ticket{i}')
            connect(f'ticket{i}',    f'security{i}')
            connect(f'security{i}',  f'gate{i}')
            connect(f'gate{i}',      'corridor1')
            connect('corridor1',     f'stairs{i}')
            connect('corridor1',     f'escalator{i}')
            connect(f'stairs{i}',    f'platform{i}')
            connect(f'escalator{i}', f'platform{i}')
            connect(f'platform{i}',  f'exit{i}')



###  热力图视图
class HeatmapView(FigureCanvas):
    """密度热力图（嵌入 Qt）"""

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(8, 6), dpi=100)
        super().__init__(self.fig)
        self.setParent(parent)
        self._draw_placeholder()

    def _draw_placeholder(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.set_facecolor('#f8f9fa')
        ax.text(0.5, 0.5, "请先开始仿真", ha='center', va='center',
                fontsize=14, color='#7f8c8d')
        ax.axis('off')
        self.draw()

    def update_view(self, graph, densities: dict):
        self.fig.clear()
        ax = self.fig.add_subplot(111)

        coords = {n: (d['x'], d['y']) for n, d in graph.nodes(data=True)}
        if not coords:
            self.draw()
            return

        nodes = list(coords.keys())
        xs    = [coords[n][0] for n in nodes]
        ys    = [coords[n][1] for n in nodes]
        vals  = [densities.get(n, 0) for n in nodes]
        vmax  = max(max(vals), 0.01)

        # 绘制边
        for u, v in graph.edges():
            if u in coords and v in coords:
                ax.plot([coords[u][0], coords[v][0]],
                        [coords[u][1], coords[v][1]],
                        color='#aab4be', linewidth=1.5, zorder=1,
                        solid_capstyle='round')

        # 绘制节点散点
        sc = ax.scatter(xs, ys, c=vals, cmap='YlOrRd', s=500,
                        alpha=0.90, edgecolors='#444', linewidths=1.2,
                        vmin=0, vmax=vmax, zorder=2)
        cbar = self.fig.colorbar(sc, ax=ax, shrink=0.7, pad=0.02)
        cbar.set_label('密度 (人/m²)', fontsize=10)
        cbar.ax.tick_params(labelsize=9)


        for n, (x, y) in coords.items():
            d_val = densities.get(n, 0)


            ax.text(x, y, n,
                    ha='center', va='center',
                    fontsize=7, fontweight='bold',
                    color='#0a4a0a', zorder=6,
                    clip_on=True)

            # 密度数值：写在节点正下方固定像素偏移处（用 transform offset）

            ax.annotate(
                f'{d_val:.3f}',
                xy=(x, y),
                xytext=(0, -22),
                textcoords='offset points',
                ha='center', va='top',
                fontsize=8,
                color='#1a5c1a',   # 深绿色
                fontweight='bold',
                zorder=6,
                bbox=dict(boxstyle='round,pad=0.15',
                          facecolor='white', edgecolor='#aaa',
                          alpha=0.90, linewidth=0.6),
            )

        ax.set_title("密度热力图", fontsize=13, fontweight='bold', pad=10)
        ax.set_facecolor('#f0f4f8')
        ax.axis('off')
        self.fig.tight_layout()
        self.draw()

    def reset(self):
        self._draw_placeholder()



#  实时数据折线图
class RealtimeDataView(QWidget):
    _DAY_START = 6 * 3600    # 06:00
    _DAY_END   = 24 * 3600   # 24:00

    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ── 操作提示 + 复位按钮 ───────────────────
        hint_row = QHBoxLayout()
        hint_lbl = QLabel("🖱 滚轮缩放  ·  拖拽平移")
        hint_lbl.setStyleSheet("color: #888; font-size: 8pt;")
        self._reset_view_btn = QPushButton("复位视图")
        self._reset_view_btn.setFixedHeight(24)
        self._reset_view_btn.setMinimumWidth(80)
        self._reset_view_btn.setStyleSheet("font-size: 8pt;")
        self._reset_view_btn.clicked.connect(self._reset_xlim)
        hint_row.addWidget(hint_lbl)
        hint_row.addStretch()
        hint_row.addWidget(self._reset_view_btn)
        main_layout.addLayout(hint_row)

        # 图表
        self.fig = Figure(figsize=(8, 5), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        main_layout.addWidget(self.canvas)

        self.ax = self.fig.add_subplot(111)
        self._start_sec = self._DAY_START
        self._total_steps = 3600

        self.time_data      = []
        self.passenger_data = []
        self.density_data   = []
        self.queue_data     = []

        self._setup_axis()

        self.line_p, = self.ax.plot([], [], 'b-',  label='乘客数量',    linewidth=2)
        self.line_d, = self.ax.plot([], [], 'g--', label='平均密度×10', linewidth=2)
        self.line_q, = self.ax.plot([], [], 'r:',  label='最长队列',    linewidth=2)
        self.ax.legend(loc='upper left', fontsize=9)

        #拖拽状态
        self._drag_x = None

        #绑定鼠标事件
        self.canvas.mpl_connect('scroll_event',         self._on_scroll)
        self.canvas.mpl_connect('button_press_event',   self._on_press)
        self.canvas.mpl_connect('motion_notify_event',  self._on_drag)
        self.canvas.mpl_connect('button_release_event', self._on_release)

    # 轴初始化
    def _setup_axis(self):
        import matplotlib.ticker as mticker
        self.ax.cla()
        self.ax.set_title("实时数据监控")
        self.ax.set_xlabel("时间")
        self.ax.set_ylabel("数值")
        self.ax.grid(True, which='major', alpha=0.3)
        self.ax.grid(True, which='minor', alpha=0.1)
        self.ax.set_xlim(self._DAY_START, self._DAY_END)

        # Y 轴始终贴左侧
        self.ax.spines['left'].set_position(('axes', 0))
        self.ax.yaxis.set_ticks_position('left')

        self.ax.xaxis.set_major_locator(mticker.MultipleLocator(3600))
        self.ax.xaxis.set_minor_locator(mticker.MultipleLocator(600))

        def _fmt(x, pos):
            h = int(x) // 3600 % 24
            m = (int(x) % 3600) // 60
            return f"{h:02d}:{m:02d}"
        self.ax.xaxis.set_major_formatter(mticker.FuncFormatter(_fmt))
        self.fig.autofmt_xdate(rotation=30, ha='right')
        self.fig.subplots_adjust(left=0.10)

    # 滚轮缩放
    def _on_scroll(self, event):
        if event.inaxes != self.ax or event.xdata is None:
            return
        xmin, xmax = self.ax.get_xlim()
        span = xmax - xmin
        factor = 0.85 if event.button == 'up' else 1.0 / 0.85
        new_span = span * factor
        cx = event.xdata
        ratio = (cx - xmin) / span
        new_xmin = cx - ratio * new_span
        new_xmax = cx + (1 - ratio) * new_span
        new_xmin = max(new_xmin, self._DAY_START)
        new_xmax = min(new_xmax, self._DAY_END)
        if new_xmax - new_xmin < 300:
            return
        self.ax.set_xlim(new_xmin, new_xmax)
        self._fit_ylim(new_xmin, new_xmax)
        self.canvas.draw_idle()

    # 拖拽平移
    def _on_press(self, event):
        if event.inaxes != self.ax or event.button != 1:
            return
        self._drag_x = event.xdata

    def _on_drag(self, event):
        if self._drag_x is None or event.inaxes != self.ax or event.xdata is None:
            return
        dx = self._drag_x - event.xdata
        xmin, xmax = self.ax.get_xlim()
        span = xmax - xmin
        new_xmin = xmin + dx
        new_xmax = xmax + dx
        if new_xmin < self._DAY_START:
            new_xmin = self._DAY_START
            new_xmax = self._DAY_START + span
        if new_xmax > self._DAY_END:
            new_xmax = self._DAY_END
            new_xmin = self._DAY_END - span
        self.ax.set_xlim(new_xmin, new_xmax)
        self._fit_ylim(new_xmin, new_xmax)
        self.canvas.draw_idle()

    def _on_release(self, event):
        self._drag_x = None

    # 复位
    def _reset_xlim(self):
        self.ax.set_xlim(self._DAY_START, self._DAY_END)
        self.ax.relim()
        self.ax.autoscale_view(scalex=False)
        self.canvas.draw_idle()

    # Y 轴随可见数据自适应
    def _fit_ylim(self, xmin, xmax):
        visible = [v for t, p, d, q in zip(self.time_data, self.passenger_data,
                                            self.density_data, self.queue_data)
                   if xmin <= t <= xmax for v in (p, d, q)]
        if visible:
            lo, hi = min(visible), max(visible)
            margin = (hi - lo) * 0.1 or 1
            self.ax.set_ylim(lo - margin, hi + margin)

    # 外部接口
    def set_start_hour(self, hour):
        self._start_sec = hour * 3600

    def set_total_steps(self, steps):
        self._total_steps = steps

    def mark_finished(self):
        pass   # 接口兼容保留

    def update_data(self, step, passengers, avg_density=0, max_queue=0):
        abs_sec = self._start_sec + step
        if abs_sec > self._DAY_END:
            return
        self.time_data.append(abs_sec)
        self.passenger_data.append(passengers)
        self.density_data.append(avg_density * 10)
        self.queue_data.append(max_queue)

        self.line_p.set_data(self.time_data, self.passenger_data)
        self.line_d.set_data(self.time_data, self.density_data)
        self.line_q.set_data(self.time_data, self.queue_data)
        self.ax.relim()
        self.ax.autoscale_view(scalex=False)
        self.canvas.draw_idle()

    def reset(self):
        self.time_data      = []
        self.passenger_data = []
        self.density_data   = []
        self.queue_data     = []
        self._drag_x        = None
        self._start_sec     = self._DAY_START
        self._setup_axis()
        self.line_p, = self.ax.plot([], [], 'b-',  label='乘客数量',    linewidth=2)
        self.line_d, = self.ax.plot([], [], 'g--', label='平均密度×10', linewidth=2)
        self.line_q, = self.ax.plot([], [], 'r:',  label='最长队列',    linewidth=2)
        self.ax.legend(loc='upper left', fontsize=9)
        self.canvas.draw()



##  分析报告视图
class AnalyticsView(QWidget):
    """文字版分析报告"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText("分析报告将在仿真结束后显示...")
        layout.addWidget(self.text_edit)

    def update_report(self, report: dict):
        lines = ["=" * 40, "  分析报告", "=" * 40, ""]

        ps = report.get('passenger_stats')
        if ps:
            lines += [
                "【乘客统计】",
                f"  乘客总数     : {ps.get('passenger_count', 0)}",
                f"  平均等待时间 : {ps.get('average_wait_time', 0):.2f} 秒",
                f"  最大等待时间 : {ps.get('max_wait_time', 0):.2f} 秒",
                f"  状态分布     : {ps.get('state_distribution', {})}",
                "",
            ]

        fs = report.get('finished_stats')
        if fs:
            lines += [
                "【已完成乘客】",
                f"  总人数       : {fs.get('finished_count', 0)}",
                f"  平均等待时间 : {fs.get('avg_wait_time', 0):.1f} 秒",
                f"  平均通行时间 : {fs.get('avg_travel_time', 0):.1f} 秒",
                "",
            ]

        ds = report.get('density_stats')
        if ds:
            lines += [
                "【密度统计】",
                f"  平均密度 : {ds.get('average_density', 0):.4f} 人/m²",
                f"  最大密度 : {ds.get('max_density', 0):.4f} 人/m²",
                f"  拥堵节点 : {ds.get('congested_nodes', [])}",
                "",
            ]

        bn = report.get('bottlenecks', [])
        if bn:
            lines += ["【瓶颈节点 Top5】"]
            for b in bn[:5]:
                lines.append(f"  {b['node_id']}: 平均密度={b['avg_density']}, "
                           f"高密度占比={b['high_density_ratio']*100:.1f}%")
            lines.append("")

        top = report.get('top_congested_nodes', [])
        if top:
            lines += ["【最拥堵 Top5】"]
            for t in top[:5]:
                lines.append(f"  {t['node_id']}: {t['avg_density']}")
            lines.append("")

        vc = report.get('visit_counts', {})
        if vc:
            lines.append("【累计访问量 Top10】")
            for node, cnt in sorted(vc.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"  {node:<20} : {cnt}")

        self.text_edit.setPlainText("\n".join(lines))

    def reset(self):
        self.text_edit.setPlainText("分析报告将在仿真结束后显示...")


##  轨迹回放视图
class TrajectoryPlaybackView(QWidget):
    """实时轨迹回放：支持快进/慢放/暂停，回放仿真历史状态"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = []
        self.current_idx = 0
        self.playing = False
        self.speed = 1.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── 控制栏 ──
        ctrl = QHBoxLayout()
        self.play_btn = QPushButton("▶ 播放")
        self.pause_btn = QPushButton("⏸ 暂停")
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "1x", "2x", "5x", "10x"])
        self.speed_combo.setCurrentIndex(1)
        self.step_label = QLabel("Step: 0 / 0")
        self.step_label.setFont(QFont("Arial", 9))

        ctrl.addWidget(self.play_btn)
        ctrl.addWidget(self.pause_btn)
        ctrl.addWidget(QLabel("速度:"))
        ctrl.addWidget(self.speed_combo)
        ctrl.addStretch()
        ctrl.addWidget(self.step_label)
        layout.addLayout(ctrl)

        # ── 时间轴滑块 ──
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.slider)

        # ── 拓扑图显示（复用 TopologyView）──
        self.topology_view = TopologyView()
        # 回放模式下禁用节点拖拽和编辑
        for item in self.topology_view.scene.items():
            if isinstance(item, NodeItem):
                item.setFlag(QGraphicsEllipseItem.ItemIsMovable, False)
                item.setFlag(QGraphicsEllipseItem.ItemIsSelectable, False)
        layout.addWidget(self.topology_view, 1)

        self.play_btn.clicked.connect(self._play)
        self.pause_btn.clicked.connect(self._pause)
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)

    def set_graph(self, graph):
        """根据当前拓扑图重建回放视图"""
        self.topology_view.scene.clear()
        self.topology_view.node_items.clear()
        self.topology_view.edge_items.clear()
        for node_id, data in graph.nodes(data=True):
            item = NodeItem(
                node_id, data.get('type', 'corridor'),
                data.get('x', 0), data.get('y', 0),
                capacity=data.get('capacity', 50),
                area=data.get('area', 100.0),
                base_speed=data.get('base_speed', 1.0),
                floor=data.get('floor', 0)
            )
            item.setFlag(QGraphicsEllipseItem.ItemIsMovable, False)
            item.setFlag(QGraphicsEllipseItem.ItemIsSelectable, False)
            self.topology_view.scene.addItem(item)
            self.topology_view.node_items[node_id] = item
        for u, v in graph.edges():
            if u in self.topology_view.node_items and v in self.topology_view.node_items:
                edge = EdgeItem(self.topology_view.node_items[u], self.topology_view.node_items[v])
                self.topology_view.scene.addItem(edge)
                self.topology_view.edge_items[(u, v)] = edge

    def set_history(self, history):
        self.history = history
        self.slider.setMaximum(max(0, len(history) - 1))
        self.current_idx = 0
        self.slider.setValue(0)
        self._update_frame()

    def _play(self):
        if not self.history:
            return
        self.playing = True
        interval = max(20, int(100 / self.speed))
        self._timer.start(interval)

    def _pause(self):
        self.playing = False
        self._timer.stop()

    def _next_frame(self):
        if self.current_idx < len(self.history) - 1:
            self.current_idx += 1
            self.slider.setValue(self.current_idx)
            self._update_frame()
        else:
            self._pause()

    def _on_slider_changed(self, value):
        self.current_idx = value
        self._update_frame()

    def _on_speed_changed(self, text):
        self.speed = float(text.replace('x', ''))
        if self.playing:
            self._timer.stop()
            interval = max(20, int(100 / self.speed))
            self._timer.start(interval)

    def _update_frame(self):
        if not self.history or self.current_idx >= len(self.history):
            return
        data = self.history[self.current_idx]
        total_step = self.history[-1]['step'] if self.history else 0
        self.step_label.setText(f"Step: {data['step']} / {total_step}")

        densities = data.get('densities', {})
        node_counts = data.get('node_counts', {})
        max_val = max(densities.values()) if densities else 1.0
        max_val = max(max_val, 0.001)

        for node_id, item in self.topology_view.node_items.items():
            item.update_passenger_count(node_counts.get(node_id, 0))
            val = densities.get(node_id, 0)
            item.update_congestion(val / max_val)

        # 边拥堵色同步更新
        for (f, t), edge_item in self.topology_view.edge_items.items():
            cf = (densities.get(f, 0) + densities.get(t, 0)) / (2 * max_val + 1e-6)
            edge_item.update_congestion(1.0 + cf * 2)

    def reset(self):
        self.history = []
        self.current_idx = 0
        self.playing = False
        self._timer.stop()
        self.slider.setMaximum(0)
        self.slider.setValue(0)
        self.step_label.setText("Step: 0 / 0")
        self.topology_view.reset()


##  仿真业务层
class SubwaySimulation:
    """封装仿真引擎的业务类"""

    def __init__(self, station_size="中型站", operation_time="",
                 custom_graph=None, total_steps=3600,
                 period_rules=None, start_hour=6):
        self.station_size   = station_size
        self.operation_time = operation_time
        self.total_steps    = total_steps

        self.peak_hours = [(0, total_steps)]

        self.station_graph = custom_graph if custom_graph else self._create_station_graph()
        self.path_planner  = PathPlanner(self.station_graph)
        self.simulation    = SimulationEngine(
            self.station_graph, self.path_planner, self.peak_hours,
            period_rules=period_rules, start_hour=start_hour
        )
        self.analytics     = AnalyticsModule(self.station_graph)

    def _parse_operation_time(self, s):
        try:
            result = []
            for part in s.split(','):
                a, b = part.split('-')
                result.append((int(a.strip()), int(b.strip())))
            return result
        except Exception:
            return [(7, 9), (17, 19)]

    def _create_station_graph(self):
        graph = StationGraph()
        cfg = {
            "小型站": dict(ec=30, tc=20, sc=15, gc=10, cc=80,  pc=150, xc=30, n=1),
            "中型站": dict(ec=50, tc=30, sc=20, gc=15, cc=100, pc=200, xc=50, n=2),
            "大型站": dict(ec=80, tc=50, sc=30, gc=25, cc=150, pc=300, xc=80, n=3),
            "换乘站": dict(ec=100, tc=60, sc=40, gc=30, cc=200, pc=400, xc=100, n=4),
        }
        c = cfg.get(self.station_size, cfg["中型站"])
        n = c['n']

        # 多楼层：floor=0 地面层，floor=1 站厅层，floor=-1 站台层
        for i in range(1, n + 1):
            y_offset = (i - 1) * 80
            # 地面层
            graph.add_node(f'entrance{i}',  'entrance',  c['ec'], 0,  10 + y_offset,
                           floor=0, area=120.0, base_speed=1.2)
            graph.add_node(f'exit{i}',      'exit',      c['xc'], 600, 10 + y_offset,
                           floor=0, area=100.0, base_speed=1.2)
            # 站厅层
            graph.add_node(f'ticket{i}',    'ticket',    c['tc'], 80, 10 + y_offset,
                           floor=1, area=80.0, base_speed=0.8, service_rate=0.4)
            graph.add_node(f'security{i}',  'security',  c['sc'], 160, 10 + y_offset,
                           floor=1, area=60.0, base_speed=0.6, service_rate=0.25)
            graph.add_node(f'gate{i}',      'gate',      c['gc'], 240, 10 + y_offset,
                           floor=1, area=40.0, base_speed=1.0, service_rate=0.6)
            # 站台层
            graph.add_node(f'stairs{i}',    'stairs',    10,      400, 10 + y_offset,
                           floor=-1, area=30.0, base_speed=0.5)
            graph.add_node(f'escalator{i}', 'escalator', 20,      400, 30 + y_offset,
                           floor=-1, area=50.0, base_speed=0.8)
            graph.add_node(f'platform{i}',  'platform',  c['pc'], 500, 20 + y_offset,
                           floor=-1, area=400.0, base_speed=1.0, dwell_time=30)

        graph.add_node('corridor1', 'corridor', c['cc'], 320, 40 + (n-1)*40,
                       floor=1, area=300.0, base_speed=1.2)

        for i in range(1, n + 1):
            graph.add_edge(f'entrance{i}',  f'ticket{i}',    20, 3, capacity=15, base_time=2.0)
            graph.add_edge(f'ticket{i}',    f'security{i}',  20, 3, capacity=10, base_time=2.0)
            graph.add_edge(f'security{i}',  f'gate{i}',      15, 3, capacity=8,  base_time=1.5)
            graph.add_edge(f'gate{i}',      'corridor1',     25, 4, capacity=20, base_time=3.0)
            graph.add_edge('corridor1',     f'stairs{i}',    30, 3, capacity=8,  base_time=4.0)
            graph.add_edge('corridor1',     f'escalator{i}', 30, 4, capacity=12, base_time=3.0)
            graph.add_edge(f'stairs{i}',    f'platform{i}',  40, 2, capacity=6,  base_time=8.0)
            graph.add_edge(f'escalator{i}', f'platform{i}',  40, 3, capacity=10, base_time=5.0)
            graph.add_edge(f'platform{i}',  f'exit{i}',      30, 3, capacity=15, base_time=3.0)

        return graph

    def run_simulation_step(self):
        self.simulation.step()

    def generate_analytics(self):
        passengers = self.simulation.get_passengers()
        densities  = {
            node: (self.station_graph.get_node(node) or {}).get('current_density', 0)
            for node in self.station_graph.get_graph().nodes()
        }
        self.analytics.record_data(self.simulation.get_current_time(), passengers, densities)
        report = self.analytics.generate_report()
        # 合并已完成乘客统计
        finished = self.simulation.get_finished_stats()
        if finished:
            report['finished_stats'] = finished
        return report


##  主窗口
class SubwaySimulationGUI(QMainWindow):
    """地铁站人流仿真系统主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("地铁站人流仿真系统")
        self.setWindowIcon(QIcon("icon.png"))
        self.setGeometry(80, 80, 1280, 820)


        _app_font = _get_qt_chinese_font(9)
        QApplication.setFont(_app_font)

        self.simulation        = None
        self.simulation_thread = None

        # 中心部件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        # 左侧控制面板
        ctrl_panel = QWidget()
        ctrl_panel.setFixedWidth(260)
        ctrl_layout = QVBoxLayout(ctrl_panel)

        # 控制按钮组
        btn_frame = QFrame()
        btn_frame.setFrameShape(QFrame.Box)
        btn_layout = QVBoxLayout(btn_frame)
        btn_layout.addWidget(QLabel("── 仿真控制 ──"))

        row1 = QHBoxLayout()
        self.start_btn = QPushButton("开始")
        self.pause_btn = QPushButton("暂停")
        row1.addWidget(self.start_btn)
        row1.addWidget(self.pause_btn)
        btn_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.stop_btn  = QPushButton("停止")
        self.reset_btn = QPushButton("重置")
        row2.addWidget(self.stop_btn)
        row2.addWidget(self.reset_btn)
        btn_layout.addLayout(row2)

        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)

        self.start_btn.clicked.connect(self.start_simulation)
        self.pause_btn.clicked.connect(self.pause_simulation)
        self.stop_btn.clicked.connect(self.stop_simulation)
        self.reset_btn.clicked.connect(self.reset_simulation)

        # 参数组
        param_frame = QFrame()
        param_frame.setFrameShape(QFrame.Box)
        param_layout = QVBoxLayout(param_frame)
        param_layout.addWidget(QLabel("── 仿真参数 ──"))

        def param_row(label, widget):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(widget)
            param_layout.addLayout(row)

        self.steps_edit      = QLineEdit("60")
        self.path_mode_combo = QComboBox()
        self.path_mode_combo.addItems(["最短时间", "最短距离", "多目标优化", "最少区域切换"])
        self.station_size_combo = QComboBox()
        self.station_size_combo.addItems(["小型站", "中型站", "大型站", "换乘站"])
        self.start_hour_combo = QComboBox()
        self.start_hour_combo.addItems([f"{h:02d}:00" for h in range(6, 24)])
        self.start_hour_combo.setCurrentIndex(0)   # 默认 06:00

        param_row("时长 (分钟):", self.steps_edit)
        param_row("起始时间:",    self.start_hour_combo)
        param_row("路径模式:",    self.path_mode_combo)
        param_row("站点规模:",    self.station_size_combo)

        # 时段流量配置
        self._period_rules = None
        self._period_config_btn = QPushButton("配置时段流量...")
        self._period_config_btn.clicked.connect(self._open_period_config)
        self._period_summary_label = QLabel("未配置（全程平常期）")
        self._period_summary_label.setStyleSheet("color: #666; font-size: 8pt;")
        param_layout.addWidget(self._period_config_btn)
        param_layout.addWidget(self._period_summary_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_label = QLabel("00:00 / 00:00")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setFont(QFont("Arial", 9))
        param_layout.addWidget(self.progress_bar)
        param_layout.addWidget(self.progress_label)

        ctrl_layout.addWidget(btn_frame)
        ctrl_layout.addWidget(param_frame)
        ctrl_layout.addStretch()

        # 右侧主显示
        self.tab_widget = QTabWidget()

        self.topology_view   = TopologyView()
        self.heatmap_view    = HeatmapView()
        self.realtime_view   = RealtimeDataView()
        self.analytics_view  = AnalyticsView()
        self.trajectory_view = TrajectoryPlaybackView()

        self.tab_widget.addTab(self.topology_view,   "拓扑图")
        self.tab_widget.addTab(self.heatmap_view,    "热力图")
        self.tab_widget.addTab(self.realtime_view,   "实时数据")
        self.tab_widget.addTab(self.analytics_view,  "分析报告")
        self.tab_widget.addTab(self.trajectory_view, "轨迹回放")

        main_layout.addWidget(ctrl_panel)
        main_layout.addWidget(self.tab_widget, 1)

        # UI刷新定时器（15 FPS，仿真与UI解耦）
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._on_ui_refresh)
        self.ui_timer.setInterval(66)  # ~15 FPS
        self._last_ui_step = 0

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 — 可在拓扑图中添加/编辑节点后开始仿真")


    ##  仿真控制
    def start_simulation(self):
        self.status_bar.showMessage("运行中...")
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)

        duration_min = max(1, int(self.steps_edit.text() or 60))
        steps = duration_min * 60   # 1分钟=60步=60秒
        self._sim_start_hour = self.start_hour_combo.currentIndex() + 6

        graph = self.topology_view.get_graph()
        self.simulation = SubwaySimulation(
            station_size   = self.station_size_combo.currentText(),
            operation_time = "",
            custom_graph   = graph,
            total_steps    = steps,
            period_rules   = self._period_rules,
            start_hour     = self._sim_start_hour,
        )

        self.progress_bar.setRange(0, steps)
        self.progress_bar.setValue(0)
        start_h = self._sim_start_hour
        self.progress_label.setText(f"{start_h:02d}:00 / {start_h:02d}:00")

        self.realtime_view.reset()
        self.realtime_view.set_start_hour(self._sim_start_hour)
        self.realtime_view.set_total_steps(steps)

        self.simulation_thread = SimulationThread(self.simulation, steps)
        self.simulation_thread.finished_signal.connect(self._on_finished)
        self.simulation_thread.start()
        self.ui_timer.start()      # 启动独立UI刷新定时器
        self._last_ui_step = 0

    def _open_period_config(self):
        dlg = PeriodConfigDialog(self._period_rules, self)
        if dlg.exec_() == QDialog.Accepted:
            self._period_rules = dlg.get_rules()
            self._period_summary_label.setText(
                PeriodConfigDialog.rules_summary(self._period_rules))

    def pause_simulation(self):
        if not self.simulation_thread:
            return
        if self.simulation_thread.paused:
            self.simulation_thread.resume()
            self.pause_btn.setText("暂停")
            self.status_bar.showMessage("运行中...")
        else:
            self.simulation_thread.pause()
            self.pause_btn.setText("继续")
            self.status_bar.showMessage("已暂停")

    def stop_simulation(self):
        self.ui_timer.stop()
        if self.simulation_thread:
            self.simulation_thread.stop()
            self.simulation_thread.wait()
        self._set_stopped_state()
        self._generate_report()

    def reset_simulation(self):
        self.ui_timer.stop()
        if self.simulation_thread:
            self.simulation_thread.stop()
            self.simulation_thread.wait()
        self.simulation        = None
        self.simulation_thread = None
        self.progress_bar.setValue(0)
        self.progress_label.setText("00:00 / 00:00")
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self.topology_view.reset()
        self.heatmap_view.reset()
        self.realtime_view.reset()
        self.analytics_view.reset()
        self.trajectory_view.reset()
        self.status_bar.showMessage("已重置")

    def _set_stopped_state(self):
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("暂停")
        self.stop_btn.setEnabled(False)
        self.reset_btn.setEnabled(True)
        self.status_bar.showMessage("已停止")


    ##  UI与仿真线程分离：独立QTimer刷新界面
    def _on_ui_refresh(self):
        """由QTimer定时调用，从仿真引擎拉取当前状态刷新UI（~15 FPS）"""
        if not self.simulation_thread or not self.simulation or not self.simulation_thread.running:
            return
        step = self.simulation_thread.current_step
        if step == 0 or step == self._last_ui_step:
            return
        self._last_ui_step = step

        # 从仿真引擎读取当前状态
        passenger_count = len(self.simulation.simulation.get_passengers())
        densities = {}
        total_density = 0
        node_count = 0
        max_queue = 0
        for node in self.simulation.station_graph.get_graph().nodes():
            node_info = self.simulation.station_graph.get_node(node)
            if node_info:
                density = node_info.get('current_density', 0)
                densities[node] = density
                total_density += density
                node_count += 1
        avg_density = total_density / node_count if node_count > 0 else 0
        for node_id, queue in self.simulation.simulation.queues.items():
            queue_length = len(queue)
            if queue_length > max_queue:
                max_queue = queue_length

        self._update_ui(step, passenger_count, densities, avg_density, max_queue)

    def _update_ui(self, step, passenger_count, densities, avg_density, max_queue):
        """统一UI刷新逻辑（进度条、拓扑图、热力图、实时数据）"""
        total = self.progress_bar.maximum()
        self.progress_bar.setValue(step)
        start_sec = getattr(self, '_sim_start_hour', 6) * 3600
        cur_sec  = start_sec + step
        end_sec  = start_sec + total
        def _fmt(s):
            h = (s // 3600) % 24
            m = (s % 3600) // 60
            return f"{h:02d}:{m:02d}"
        self.progress_label.setText(f"{_fmt(cur_sec)} / {_fmt(end_sec)}")
        self.status_bar.showMessage(
            f"运行中 — {_fmt(cur_sec)}  乘客: {passenger_count}  平均密度: {avg_density:.3f}"
        )
        if not self.simulation:
            return

        graph      = self.simulation.station_graph.get_graph()
        passengers = self.simulation.simulation.get_passengers()

        self.topology_view.update_view(graph, passengers)
        self.topology_view.update_congestion(densities)
        self.heatmap_view.update_view(graph, densities)
        self.realtime_view.update_data(step, passenger_count, avg_density, max_queue)

    def _on_finished(self, history):
        """仿真结束：停止UI定时器，加载轨迹回放数据"""
        self.ui_timer.stop()
        self._set_stopped_state()
        self.status_bar.showMessage("仿真完成")
        # 加载轨迹回放到回放视图
        if history:
            graph = self.simulation.station_graph.get_graph() if self.simulation else None
            if graph:
                self.trajectory_view.set_graph(graph)
            self.trajectory_view.set_history(history)
        self._generate_report()

    def _generate_report(self):
        if self.simulation:
            report = self.simulation.generate_analytics()
            self.analytics_view.update_report(report)
            self.tab_widget.setCurrentIndex(3)   # 自动跳到分析报告



##  入口
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(_get_qt_chinese_font(9))
    import os

    _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    app.setWindowIcon(QIcon(_icon_path))

    window = SubwaySimulationGUI()
    window.show()
    sys.exit(app.exec_())