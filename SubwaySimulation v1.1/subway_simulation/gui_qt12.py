from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTextEdit,
    QTabWidget, QProgressBar, QStatusBar, QFrame, QSplitter,
    QTableWidget, QTableWidgetItem, QGridLayout, QGraphicsScene,
    QGraphicsView, QGraphicsEllipseItem, QGraphicsLineItem, QDialog,
    QFormLayout, QDoubleSpinBox, QSpinBox, QMessageBox, QGraphicsTextItem,
    QSizePolicy, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPointF, QRectF, QDate
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QBrush, QCursor, QIcon
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.font_manager as _fm
import networkx as nx
import sys
import time
import datetime
import pandas as pd
from core import StationGraph, SimulationEngine, PathPlanner, AnalyticsModule

# ── 自动检测并设置可用中文字体 ──
_CHINESE_FONT_PRIORITY = [
    'SimHei', 'Microsoft YaHei', 'PingFang SC',
    'WenQuanYi Zen Hei', 'WenQuanYi Micro Hei',
    'Noto Sans CJK SC', 'Noto Sans SC',
    'Source Han Sans CN', 'AR PL UMing CN',
    'DejaVu Sans',
]
_available_fonts = {f.name for f in _fm.fontManager.ttflist}
_chosen_font = next((f for f in _CHINESE_FONT_PRIORITY if f in _available_fonts), 'DejaVu Sans')
plt.rcParams['font.sans-serif'] = [_chosen_font]
plt.rcParams['axes.unicode_minus'] = False

def _get_qt_chinese_font(size=9) -> "QFont":
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
    return QFont(size)

# ── 全局：一年期模拟数据存储（从1月1日开始） ──
simulation_history = pd.DataFrame(columns=[
    "sim_date", "station_size", "total_steps", "total_passengers",
    "avg_density", "max_density", "avg_wait_time", "max_queue"
])

def get_next_simulation_date():
    """获取下一个模拟日期，从1月1日开始，一年内递增"""
    if simulation_history.empty:
        # 默认从当年1月1日开始
        return datetime.date(datetime.date.today().year, 1, 1)
    else:
        last_date = pd.to_datetime(simulation_history["sim_date"]).max().date()
        next_date = last_date + datetime.timedelta(days=1)
        # 限制在同一年内
        if next_date.year > last_date.year:
            next_date = datetime.date(last_date.year, 1, 1)
        return next_date

# ─────────────────────────────────────────────
#  仿真线程
# ─────────────────────────────────────────────
class SimulationThread(QThread):
    update_signal = pyqtSignal(int, int, dict, float, int)
    finished_signal = pyqtSignal()

    def __init__(self, simulation, steps):
        super().__init__()
        self.simulation = simulation
        self.steps = steps
        self.running = True
        self.paused = False

    def run(self):
        for i in range(self.steps):
            if not self.running:
                break
            while self.paused:
                time.sleep(0.1)
                if not self.running:
                    break
            if not self.running:
                break
            self.simulation.run_simulation_step()
            if (i + 1) % 10 == 0:
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
                self.update_signal.emit(i + 1, passenger_count, densities, avg_density, max_queue)
            time.sleep(0.1)
        self.finished_signal.emit()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.running = False
        self.paused = False

# ─────────────────────────────────────────────
#  节点图形项
# ─────────────────────────────────────────────
class NodeItem(QGraphicsEllipseItem):
    NODE_RADIUS = 12
    def __init__(self, node_id, node_type, x, y, capacity=50, area=100.0, base_speed=1.0, parent=None):
        r = NodeItem.NODE_RADIUS
        super().__init__(-r, -r, r * 2, r * 2, parent)
        self.node_id = node_id
        self.node_type = node_type
        self.capacity = capacity
        self.area = area
        self.base_speed = base_speed
        self.setPos(x, y)
        self.setBrush(self._get_brush())
        self.setPen(QPen(QColor('black'), 2))
        self.setFlag(QGraphicsEllipseItem.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsEllipseItem.ItemSendsGeometryChanges, True)
        self.id_text = QGraphicsTextItem(node_id, self)
        self.id_text.setPos(-r, -r - 18)
        self.id_text.setDefaultTextColor(QColor('black'))
        self.count_text = QGraphicsTextItem("0人", self)
        self.count_text.setPos(-r, r + 2)
        self.count_text.setDefaultTextColor(QColor('#333333'))
        self._base_pen = QPen(QColor('black'), 2)
        self._congestion_pen = QPen(QColor('red'), 3)

    _COLOR_MAP = {
        'entrance': '#27ae60', 'exit': '#e74c3c', 'security': '#f39c12',
        'ticket': '#2980b9', 'gate': '#e67e22', 'platform': '#8e44ad',
        'corridor': '#7f8c8d', 'stairs': '#795548', 'escalator': '#f48fb1',
    }

    def _get_brush(self):
        color = self._COLOR_MAP.get(self.node_type, '#ffffff')
        return QBrush(QColor(color))

    def update_congestion(self, congestion):
        base = QColor(self._COLOR_MAP.get(self.node_type, '#ffffff'))
        r = min(255, base.red() + int(congestion * 80))
        g = max(0, base.green() - int(congestion * 80))
        b = max(0, base.blue() - int(congestion * 80))
        self.setBrush(QBrush(QColor(r, g, b)))
        if congestion > 0.6:
            self.setPen(self._congestion_pen)
        else:
            self.setPen(self._base_pen)

    def update_passenger_count(self, count):
        self.count_text.setPlainText(f"{count}人")

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsEllipseItem.ItemPositionHasChanged:
            if self.scene():
                for item in self.scene().items():
                    if isinstance(item, EdgeItem):
                        if item.from_node is self or item.to_node is self:
                            item.update_position()
        return result

# ─────────────────────────────────────────────
#  边图形项
# ─────────────────────────────────────────────
class EdgeItem(QGraphicsLineItem):
    def __init__(self, from_node, to_node, parent=None):
        super().__init__(parent)
        self.from_node = from_node
        self.to_node = to_node
        self.setPen(QPen(QColor('#2c3e50'), 2))
        self.setZValue(-1)
        self.update_position()

    def update_position(self):
        if self.from_node and self.to_node:
            fp = self.from_node.scenePos()
            tp = self.to_node.scenePos()
            self.setLine(fp.x(), fp.y(), tp.x(), tp.y())

    def update_congestion(self, congestion_factor):
        width = max(2, min(8, int(congestion_factor * 2)))
        ratio = min(1.0, (congestion_factor - 1.0) / 2.0)
        r = int(44 + ratio * (231 - 44))
        g = int(62 + ratio * (76 - 62))
        b = int(80 - ratio * 80)
        self.setPen(QPen(QColor(r, g, b), width))

# ─────────────────────────────────────────────
#  节点属性对话框
# ─────────────────────────────────────────────
class NodeDialog(QDialog):
    NODE_TYPES = ['entrance', 'exit', 'security', 'ticket', 'gate', 'platform', 'corridor', 'stairs', 'escalator']
    def __init__(self, parent=None, node_data=None, existing_ids=None):
        super().__init__(parent)
        self.existing_ids = existing_ids or set()
        self._original_id = node_data.get('id', '') if node_data else ''
        self.setWindowTitle("节点属性")
        self.setFixedSize(340, 295)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        _num_font = QFont("Arial", 10)
        _text_font = _get_qt_chinese_font(10)
        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignRight)
        layout.setSpacing(10)
        self.id_edit = QLineEdit()
        self.id_edit.setFont(_text_font)
        layout.addRow("节点 ID:", self.id_edit)
        self.type_combo = QComboBox()
        self.type_combo.setFont(_text_font)
        self.type_combo.addItems(self.NODE_TYPES)
        layout.addRow("节点类型:", self.type_combo)
        self.capacity_spin = QSpinBox()
        self.capacity_spin.setFont(_num_font)
        self.capacity_spin.setRange(1, 1000)
        self.capacity_spin.setValue(50)
        layout.addRow("容量 (人):", self.capacity_spin)
        self.area_spin = QDoubleSpinBox()
        self.area_spin.setFont(_num_font)
        self.area_spin.setRange(10.0, 10000.0)
        self.area_spin.setDecimals(1)
        self.area_spin.setSingleStep(10.0)
        self.area_spin.setValue(100.0)
        layout.addRow("面积 (m2):", self.area_spin)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setFont(_num_font)
        self.speed_spin.setRange(0.1, 3.0)
        self.speed_spin.setDecimals(2)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(1.0)
        layout.addRow("速度 (m/s):", self.speed_spin)
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
        if node_data:
            self.id_edit.setText(node_data.get('id', ''))
            self.type_combo.setCurrentText(node_data.get('type', 'entrance'))
            self.capacity_spin.setValue(node_data.get('capacity', 50))
            self.area_spin.setValue(node_data.get('area', 100.0))
            self.speed_spin.setValue(node_data.get('base_speed', 1.0))

    def _on_accept(self):
        node_id = self.id_edit.text().strip()
        if not node_id:
            QMessageBox.warning(self, "输入错误", "节点 ID 不能为空！")
            return
        if node_id != self._original_id and node_id in self.existing_ids:
            QMessageBox.warning(self, "输入错误", f"节点 ID「{node_id}」已存在！")
            return
        self.accept()

    def get_data(self):
        return {
            'id': self.id_edit.text().strip(),
            'type': self.type_combo.currentText(),
            'capacity': self.capacity_spin.value(),
            'area': self.area_spin.value(),
            'base_speed': self.speed_spin.value(),
        }

# ─────────────────────────────────────────────
#  拓扑图视图
# ─────────────────────────────────────────────
class TopologyView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        self.add_node_btn = QPushButton("添加节点")
        self.add_edge_btn = QPushButton("添加边")
        self.delete_btn = QPushButton("删除选中")
        legend_label = QLabel(
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
        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QBrush(QColor('#f8f9fa')))
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing, True)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.setSceneRect(0, 0, 900, 620)
        main_layout.addWidget(self.view)
        self.add_node_mode = False
        self.add_edge_mode = False
        self.start_node = None
        self.temp_edge = None
        self.node_items = {}
        self.edge_items = {}
        self.add_node_btn.clicked.connect(self.toggle_add_node_mode)
        self.add_edge_btn.clicked.connect(self.toggle_add_edge_mode)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.view.mousePressEvent = self._mouse_press
        self.view.mouseMoveEvent = self._mouse_move
        self.view.mouseReleaseEvent = self._mouse_release
        self.view.mouseDoubleClickEvent = self._mouse_double_click
        self._load_default_topology()

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

    def _create_node_at(self, scene_x, scene_y):
        dialog = NodeDialog(self, existing_ids=set(self.node_items.keys()))
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            node_id = data['id']
            if node_id:
                item = NodeItem(node_id, data['type'], scene_x, scene_y, capacity=data['capacity'], area=data['area'], base_speed=data['base_speed'])
                self.scene.addItem(item)
                self.node_items[node_id] = item

    def delete_selected(self):
        for item in list(self.scene.selectedItems()):
            if isinstance(item, NodeItem):
                self._remove_node(item)
            elif isinstance(item, EdgeItem):
                self._remove_edge_item(item)

    def _remove_node(self, node_item: NodeItem):
        edges_to_del = [k for k, e in self.edge_items.items() if e.from_node is node_item or e.to_node is node_item]
        for k in edges_to_del:
            self.scene.removeItem(self.edge_items.pop(k))
        del self.node_items[node_item.node_id]
        self.scene.removeItem(node_item)

    def _remove_edge_item(self, edge_item: EdgeItem):
        key_to_del = next((k for k, e in self.edge_items.items() if e is edge_item), None)
        if key_to_del:
            del self.edge_items[key_to_del]
        self.scene.removeItem(edge_item)

    def _mouse_press(self, event):
        scene_pos = self.view.mapToScene(event.pos())
        if self.add_node_mode:
            self._create_node_at(scene_pos.x(), scene_pos.y())
            self.toggle_add_node_mode()
            return
        if self.add_edge_mode:
            item = self.view.itemAt(event.pos())
            while item and not isinstance(item, NodeItem):
                item = item.parentItem()
            if isinstance(item, NodeItem):
                if self.start_node is None:
                    self.start_node = item
                    item.setPen(QPen(QColor('#e74c3c'), 3))
                else:
                    if self.start_node is not item:
                        key = (self.start_node.node_id, item.node_id)
                        if key not in self.edge_items:
                            edge = EdgeItem(self.start_node, item)
                            self.scene.addItem(edge)
                            self.edge_items[key] = edge
                    self.start_node.setPen(QPen(QColor('black'), 2))
                    self.start_node = None
                    if self.temp_edge:
                        self.scene.removeItem(self.temp_edge)
                        self.temp_edge = None
            return
        QGraphicsView.mousePressEvent(self.view, event)

    def _mouse_move(self, event):
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

    def _mouse_double_click(self, event):
        item = self.view.itemAt(event.pos())
        while item and not isinstance(item, NodeItem):
            item = item.parentItem()
        if isinstance(item, NodeItem):
            self._edit_node(item)
        else:
            scene_pos = self.view.mapToScene(event.pos())
            self._create_node_at(scene_pos.x(), scene_pos.y())

    def _edit_node(self, item: NodeItem):
        existing = set(self.node_items.keys())
        node_data = {
            'id': item.node_id, 'type': item.node_type, 'capacity': item.capacity,
            'area': item.area, 'base_speed': item.base_speed
        }
        dialog = NodeDialog(self, node_data, existing_ids=existing)
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.get_data()
            new_id = new_data['id']
            new_type = new_data['type']
            item.capacity = new_data['capacity']
            item.area = new_data['area']
            item.base_speed = new_data['base_speed']
            if new_id != item.node_id:
                new_edges = {}
                for (f, t), e in self.edge_items.items():
                    nf = new_id if f == item.node_id else f
                    nt = new_id if t == item.node_id else t
                    new_edges[(nf, nt)] = e
                self.edge_items = new_edges
                del self.node_items[item.node_id]
                item.node_id = new_id
                item.id_text.setPlainText(new_id)
                self.node_items[new_id] = item
            if new_type != item.node_type:
                item.node_type = new_type
                item.setBrush(item._get_brush())

    def update_view(self, graph, passengers):
        node_counts = {}
        for p in passengers:
            node_counts[p.current_node] = node_counts.get(p.current_node, 0) + 1
        for node_id, item in self.node_items.items():
            item.update_passenger_count(node_counts.get(node_id, 0))

    def update_congestion(self, congestion_data: dict):
        max_val = max(congestion_data.values()) if congestion_data else 1.0
        max_val = max(max_val, 0.001)
        for node_id, val in congestion_data.items():
            if node_id in self.node_items:
                self.node_items[node_id].update_congestion(val / max_val)
        for (f, t), edge_item in self.edge_items.items():
            cf = (congestion_data.get(f, 0) + congestion_data.get(t, 0)) / (2 * max_val + 1e-6)
            edge_item.update_congestion(1.0 + cf * 2)

    def reset(self):
        self.scene.clear()
        self.node_items.clear()
        self.edge_items.clear()
        self._load_default_topology()

    def get_graph(self) -> StationGraph:
        graph = StationGraph()
        for node_id, item in self.node_items.items():
            pos = item.scenePos()
            graph.add_node(node_id, item.node_type, item.capacity, pos.x(), pos.y(), area=item.area, base_speed=item.base_speed)
        for (f, t), item in self.edge_items.items():
            fp = item.from_node.scenePos()
            tp = item.to_node.scenePos()
            dist = ((fp.x()-tp.x())**2 + (fp.y()-tp.y())**2) ** 0.5
            graph.add_edge(f, t, max(dist, 1.0), 2, capacity=10, base_time=1.0)
        return graph

    def _load_default_topology(self):
        n = 2
        layout = {
            'entrance': (60, 80), 'ticket': (180, 80), 'security': (300, 80),
            'gate': (420, 80), 'corridor': (520, 160), 'stairs': (620, 80),
            'escalator': (620, 160), 'platform': (760, 80), 'exit': (880, 80)
        }
        y_step = 120
        def add(nid, ntype, x, y):
            item = NodeItem(nid, ntype, x, y)
            self.scene.addItem(item)
            self.node_items[nid] = item
        def connect(fid, tid):
            if fid in self.node_items and tid in self.node_items:
                key = (fid, tid)
                if key not in self.edge_items:
                    edge = EdgeItem(self.node_items[fid], self.node_items[tid])
                    self.scene.addItem(edge)
                    self.edge_items[key] = edge
        for i in range(1, n+1):
            dy = (i-1)*y_step
            add(f'entrance{i}', 'entrance', layout['entrance'][0], layout['entrance'][1]+dy)
            add(f'ticket{i}', 'ticket', layout['ticket'][0], layout['ticket'][1]+dy)
            add(f'security{i}', 'security', layout['security'][0], layout['security'][1]+dy)
            add(f'gate{i}', 'gate', layout['gate'][0], layout['gate'][1]+dy)
            add(f'stairs{i}', 'stairs', layout['stairs'][0], layout['stairs'][1]+dy)
            add(f'escalator{i}', 'escalator', layout['escalator'][0], layout['escalator'][1]+dy)
            add(f'platform{i}', 'platform', layout['platform'][0], layout['platform'][1]+dy)
            add(f'exit{i}', 'exit', layout['exit'][0], layout['exit'][1]+dy)
        add('corridor1', 'corridor', layout['corridor'][0], layout['corridor'][1])
        for i in range(1, n+1):
            connect(f'entrance{i}', f'ticket{i}')
            connect(f'ticket{i}', f'security{i}')
            connect(f'security{i}', f'gate{i}')
            connect(f'gate{i}', 'corridor1')
            connect('corridor1', f'stairs{i}')
            connect('corridor1', f'escalator{i}')
            connect(f'stairs{i}', f'platform{i}')
            connect(f'escalator{i}', f'platform{i}')
            connect(f'platform{i}', f'exit{i}')

# ─────────────────────────────────────────────
#  热力图视图
# ─────────────────────────────────────────────
class HeatmapView(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(8, 6), dpi=100)
        super().__init__(self.fig)
        self.setParent(parent)
        self._draw_placeholder()

    def _draw_placeholder(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.set_facecolor('#f8f9fa')
        ax.text(0.5, 0.5, "请先开始仿真", ha='center', va='center', fontsize=14, color='#7f8c8d')
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
        xs = [coords[n][0] for n in nodes]
        ys = [coords[n][1] for n in nodes]
        vals = [densities.get(n, 0) for n in nodes]
        vmax = max(max(vals), 0.01)
        for u, v in graph.edges():
            if u in coords and v in coords:
                ax.plot([coords[u][0], coords[v][0]], [coords[u][1], coords[v][1]], color='#aab4be', linewidth=1.5, zorder=1)
        sc = ax.scatter(xs, ys, c=vals, cmap='YlOrRd', s=500, alpha=0.9, edgecolors='#444', linewidths=1.2, vmin=0, vmax=vmax, zorder=2)
        cbar = self.fig.colorbar(sc, ax=ax, shrink=0.7, pad=0.02)
        cbar.set_label('密度 (人/m²)', fontsize=10)
        for n, (x, y) in coords.items():
            d_val = densities.get(n, 0)
            ax.text(x, y, n, ha='center', va='center', fontsize=7, fontweight='bold', color='#0a4a0a', zorder=6)
            ax.annotate(f'{d_val:.3f}', xy=(x, y), xytext=(0, -22), textcoords='offset points', ha='center', va='top', fontsize=8, color='#1a5c1a', fontweight='bold', zorder=6, bbox=dict(boxstyle='round,pad=0.15', facecolor='white', edgecolor='#aaa', alpha=0.9, linewidth=0.6))
        ax.set_title("密度热力图", fontsize=13, fontweight='bold', pad=10)
        ax.set_facecolor('#f0f4f8')
        ax.axis('off')
        self.fig.tight_layout()
        self.draw()

    def reset(self):
        self._draw_placeholder()

# ─────────────────────────────────────────────
#  实时数据折线图
# ─────────────────────────────────────────────
class RealtimeDataView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.fig = Figure(figsize=(8, 5), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("实时数据监控")
        self.ax.set_xlabel("时间步")
        self.ax.set_ylabel("数值")
        self.ax.grid(True, alpha=0.3)
        self.time_data = []
        self.passenger_data = []
        self.density_data = []
        self.queue_data = []
        self.line_p, = self.ax.plot([], [], 'b-', label='乘客数量', linewidth=2)
        self.line_d, = self.ax.plot([], [], 'g--', label='平均密度×10', linewidth=2)
        self.line_q, = self.ax.plot([], [], 'r:', label='最长队列', linewidth=2)
        self.ax.legend(loc='upper left', fontsize=9)

    def update_data(self, step, passengers, avg_density=0, max_queue=0):
        self.time_data.append(step)
        self.passenger_data.append(passengers)
        self.density_data.append(avg_density * 10)
        self.queue_data.append(max_queue)
        if len(self.time_data) > 100:
            self.time_data = self.time_data[-100:]
            self.passenger_data = self.passenger_data[-100:]
            self.density_data = self.density_data[-100:]
            self.queue_data = self.queue_data[-100:]
        self.line_p.set_data(self.time_data, self.passenger_data)
        self.line_d.set_data(self.time_data, self.density_data)
        self.line_q.set_data(self.time_data, self.queue_data)
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()

    def reset(self):
        self.time_data = self.passenger_data = self.density_data = self.queue_data = []
        self.line_p.set_data([], [])
        self.line_d.set_data([], [])
        self.line_q.set_data([], [])
        self.ax.relim()
        self.canvas.draw()

# ─────────────────────────────────────────────
#  分析报告视图
# ─────────────────────────────────────────────
class AnalyticsView(QWidget):
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
                f"  状态分布     : {ps.get('state_distribution', {})}", ""
            ]
        ds = report.get('density_stats')
        if ds:
            lines += [
                "【密度统计】",
                f"  平均密度 : {ds.get('average_density', 0):.4f} 人/m²",
                f"  最大密度 : {ds.get('max_density', 0):.4f} 人/m²",
                f"  拥堵节点 : {ds.get('congested_nodes', [])}", ""
            ]
        bn = report.get('bottlenecks', [])
        if bn:
            lines += ["【瓶颈节点】", f"  {bn}", ""]
        top = report.get('top_congested_nodes', [])
        if top:
            lines += ["【最拥堵 Top5】", f"  {top}", ""]
        vc = report.get('visit_counts', {})
        if vc:
            lines.append("【累计访问量 Top10】")
            for node, cnt in sorted(vc.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"  {node:<20} : {cnt}")
        self.text_edit.setPlainText("\n".join(lines))

    def reset(self):
        self.text_edit.setPlainText("分析报告将在仿真结束后显示...")

# ─────────────────────────────────────────────
#  日历日期按钮（可点击，有记录则高亮）
# ─────────────────────────────────────────────
class CalendarDayButton(QPushButton):
    clicked_date = pyqtSignal(QDate)
    def __init__(self, date: QDate, has_record: bool, parent=None):
        super().__init__(parent)
        self.date = date
        self.has_record = has_record
        self.setText(str(date.day()))
        self.setFixedSize(70, 70)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFont(_get_qt_chinese_font(11))
        if has_record:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #f5f5f5;
                    color: #666;
                    border: none;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #e5e5e5;
                }
            """)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self):
        self.clicked_date.emit(self.date)

# ─────────────────────────────────────────────
#  全年日历视图（手机风格网格布局）
# ─────────────────────────────────────────────
class AnnualCalendarView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_year = QDate(datetime.date.today().year, 1, 1)
        self.selected_date = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        # 年份导航
        nav_layout = QHBoxLayout()
        self.year_label = QLabel()
        self.year_label.setFont(_get_qt_chinese_font(14))
        nav_layout.addStretch()
        nav_layout.addWidget(self.year_label)
        nav_layout.addStretch()
        layout.addLayout(nav_layout)
        # 滚动区域（容纳12个月网格）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.calendar_layout = QVBoxLayout(scroll_content)
        self.calendar_layout.setSpacing(10)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        # 详情展示区
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("点击有记录的日期查看模拟详情")
        layout.addWidget(self.detail_text)
        self.update_calendar()

    def update_calendar(self):
        # 清空旧布局
        while self.calendar_layout.count():
            child = self.calendar_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.year_label.setText(f"{self.current_year.year()}年")
        # 遍历12个月
        for month in range(1, 13):
            month_widget = QWidget()
            month_layout = QVBoxLayout(month_widget)
            month_layout.setSpacing(5)
            # 月份标题
            month_label = QLabel(f"{month}月")
            month_label.setFont(_get_qt_chinese_font(12))
            month_layout.addWidget(month_label)
            # 星期标题
            week_layout = QGridLayout()
            week_names = ["日", "一", "二", "三", "四", "五", "六"]
            for i, name in enumerate(week_names):
                label = QLabel(name)
                label.setAlignment(Qt.AlignCenter)
                label.setFont(_get_qt_chinese_font(10))
                week_layout.addWidget(label, 0, i)
            month_layout.addLayout(week_layout)
            # 日期网格
            grid_layout = QGridLayout()
            grid_layout.setSpacing(3)
            first_day = QDate(self.current_year.year(), month, 1)
            start_weekday = first_day.dayOfWeek()
            if start_weekday == 7:
                start_weekday = 0
            else:
                start_weekday = start_weekday
            row = 1
            col = start_weekday
            current_date = first_day
            while current_date.month() == month:
                py_date = current_date.toPyDate()
                has_record = not simulation_history[simulation_history["sim_date"] == py_date].empty
                day_btn = CalendarDayButton(current_date, has_record)
                day_btn.clicked_date.connect(self.show_date_detail)
                grid_layout.addWidget(day_btn, row, col)
                col += 1
                if col > 6:
                    col = 0
                    row += 1
                current_date = current_date.addDays(1)
            month_layout.addLayout(grid_layout)
            self.calendar_layout.addWidget(month_widget)

    def show_date_detail(self, date: QDate):
        self.selected_date = date
        py_date = date.toPyDate()
        records = simulation_history[simulation_history["sim_date"] == py_date]
        if records.empty:
            self.detail_text.setPlainText(f"{date.toString('yyyy-MM-dd')} 暂无模拟记录")
            return
        record = records.iloc[0]
        detail = f"""【{date.toString('yyyy-MM-dd')} 模拟记录】
站点规模：{record['station_size']}
仿真步数：{record['total_steps']}
总乘客数：{record['total_passengers']}
平均密度：{record['avg_density']:.4f} 人/m²
最大密度：{record['max_density']:.4f} 人/m²
平均等待时间：{record['avg_wait_time']:.2f} 秒
最长队列：{record['max_queue']} 人
"""
        self.detail_text.setPlainText(detail)

    def reset(self):
        self.current_year = QDate(datetime.date.today().year, 1, 1)
        self.selected_date = None
        self.detail_text.clear()
        self.detail_text.setPlaceholderText("点击有记录的日期查看模拟详情")
        self.update_calendar()

    def refresh_data(self):
        self.update_calendar()

# ─────────────────────────────────────────────
#  仿真业务层
# ─────────────────────────────────────────────
class SubwaySimulation:
    def __init__(self, station_size="中型站", operation_time="7-9,17-19", custom_graph=None, total_steps=100):
        self.station_size = station_size
        self.operation_time = operation_time
        self.peak_hours = [(0, total_steps)]
        self.station_graph = custom_graph if custom_graph else self._create_station_graph()
        self.path_planner = PathPlanner(self.station_graph)
        self.simulation = SimulationEngine(self.station_graph, self.path_planner, self.peak_hours)
        self.analytics = AnalyticsModule(self.station_graph)

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
            "小型站": dict(ec=30, tc=20, sc=15, gc=10, cc=80, pc=150, xc=30, n=1),
            "中型站": dict(ec=50, tc=30, sc=20, gc=15, cc=100, pc=200, xc=50, n=2),
            "大型站": dict(ec=80, tc=50, sc=30, gc=25, cc=150, pc=300, xc=80, n=3),
        }
        c = cfg.get(self.station_size, cfg["中型站"])
        n = c['n']
        for i in range(1, n+1):
            graph.add_node(f'entrance{i}', 'entrance', c['ec'], 0, 5*i, area=100.0, base_speed=1.0)
            graph.add_node(f'ticket{i}', 'ticket', c['tc'], 5, 5*i, area=80.0, base_speed=0.8)
            graph.add_node(f'security{i}', 'security', c['sc'], 10, 5*i, area=60.0, base_speed=0.6)
            graph.add_node(f'gate{i}', 'gate', c['gc'], 15, 5*i, area=40.0, base_speed=1.0)
            graph.add_node(f'stairs{i}', 'stairs', 10, 25, 5*i, area=30.0, base_speed=0.5)
            graph.add_node(f'escalator{i}', 'escalator', 20, 25, 5*i+2.5, area=50.0, base_speed=0.8)
            graph.add_node(f'platform{i}', 'platform', c['pc'], 30, 5*i, area=400.0, base_speed=1.0)
            graph.add_node(f'exit{i}', 'exit', c['xc'], 35, 5*i, area=100.0, base_speed=1.0)
        graph.add_node('corridor1', 'corridor', c['cc'], 20, 10, area=200.0, base_speed=1.2)
        for i in range(1, n+1):
            graph.add_edge(f'entrance{i}', f'ticket{i}', 5, 2, capacity=10, base_time=1.0)
            graph.add_edge(f'ticket{i}', f'security{i}', 5, 2, capacity=8, base_time=1.0)
            graph.add_edge(f'security{i}', f'gate{i}', 5, 2, capacity=5, base_time=1.0)
            graph.add_edge(f'gate{i}', 'corridor1', 5, 3, capacity=15, base_time=1.0)
            graph.add_edge('corridor1', f'stairs{i}', 5, 2, capacity=8, base_time=1.0)
            graph.add_edge('corridor1', f'escalator{i}', 5, 3, capacity=12, base_time=1.0)
            graph.add_edge(f'stairs{i}', f'platform{i}', 10, 2, capacity=6, base_time=2.0)
            graph.add_edge(f'escalator{i}', f'platform{i}', 10, 3, capacity=10, base_time=1.5)
            graph.add_edge(f'platform{i}', f'exit{i}', 5, 2, capacity=10, base_time=1.0)
        return graph

    def run_simulation_step(self):
        self.simulation.step()

    def generate_analytics(self):
        passengers = self.simulation.get_passengers()
        densities = {node: (self.station_graph.get_node(node) or {}).get('current_density', 0) for node in self.station_graph.get_graph().nodes()}
        self.analytics.record_data(self.simulation.get_current_time(), passengers, densities)
        return self.analytics.generate_report()

# ─────────────────────────────────────────────
#  主窗口
# ─────────────────────────────────────────────
class SubwaySimulationGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("地铁站人流仿真系统")
        self.setWindowIcon(QIcon("icon.png"))
        self.setGeometry(80, 80, 1280, 820)
        _app_font = _get_qt_chinese_font(9)
        QApplication.setFont(_app_font)
        self.simulation = None
        self.simulation_thread = None
        self.current_sim_date = None
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        # 左侧控制面板
        ctrl_panel = QWidget()
        ctrl_panel.setFixedWidth(260)
        ctrl_layout = QVBoxLayout(ctrl_panel)
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
        self.stop_btn = QPushButton("停止")
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
        ctrl_layout.addWidget(btn_frame)
        param_frame = QFrame()
        param_frame.setFrameShape(QFrame.Box)
        param_layout = QVBoxLayout(param_frame)
        param_layout.addWidget(QLabel("── 仿真参数 ──"))
        def param_row(label, widget):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(widget)
            param_layout.addLayout(row)
        self.steps_edit = QLineEdit("100")
        self.peak_rate_edit = QLineEdit("10")
        self.normal_rate_edit = QLineEdit("5")
        self.path_mode_combo = QComboBox()
        self.path_mode_combo.addItems(["最短时间", "最短距离", "多目标优化", "最少区域切换"])
        self.station_size_combo = QComboBox()
        self.station_size_combo.addItems(["小型站", "中型站", "大型站"])
        self.operation_time_edit = QLineEdit("7-9,17-19")
        param_row("仿真步数:", self.steps_edit)
        param_row("高峰生成率:", self.peak_rate_edit)
        param_row("平峰生成率:", self.normal_rate_edit)
        param_row("路径模式:", self.path_mode_combo)
        param_row("站点规模:", self.station_size_combo)
        param_row("高峰时段:", self.operation_time_edit)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_label = QLabel("0 / 0 步")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setFont(QFont("Arial", 9))
        param_layout.addWidget(self.progress_bar)
        param_layout.addWidget(self.progress_label)
        ctrl_layout.addWidget(param_frame)
        ctrl_layout.addStretch()
        # 右侧标签页
        self.tab_widget = QTabWidget()
        self.topology_view = TopologyView()
        self.heatmap_view = HeatmapView()
        self.realtime_view = RealtimeDataView()
        self.analytics_view = AnalyticsView()
        self.calendar_view = AnnualCalendarView()  # 新全年日历视图
        self.tab_widget.addTab(self.topology_view, "拓扑图")
        self.tab_widget.addTab(self.heatmap_view, "热力图")
        self.tab_widget.addTab(self.realtime_view, "实时数据")
        self.tab_widget.addTab(self.analytics_view, "分析报告")
        self.tab_widget.addTab(self.calendar_view, "日历数据")
        main_layout.addWidget(ctrl_panel)
        main_layout.addWidget(self.tab_widget, 1)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 — 可在拓扑图中添加/编辑节点后开始仿真")

    def start_simulation(self):
        self.status_bar.showMessage("运行中...")
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        steps = max(1, int(self.steps_edit.text() or 100))
        self.current_sim_date = get_next_simulation_date()
        self.status_bar.showMessage(f"运行中（模拟日期：{self.current_sim_date}）...")
        graph = self.topology_view.get_graph()
        self.simulation = SubwaySimulation(
            station_size=self.station_size_combo.currentText(),
            operation_time=self.operation_time_edit.text(),
            custom_graph=graph,
            total_steps=steps
        )
        self.progress_bar.setRange(0, steps)
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"0 / {steps} 步")
        self.simulation_thread = SimulationThread(self.simulation, steps)
        self.simulation_thread.update_signal.connect(self._on_update)
        self.simulation_thread.finished_signal.connect(self._on_finished)
        self.simulation_thread.start()

    def pause_simulation(self):
        if not self.simulation_thread:
            return
        if self.simulation_thread.paused:
            self.simulation_thread.resume()
            self.pause_btn.setText("暂停")
            self.status_bar.showMessage(f"运行中（模拟日期：{self.current_sim_date}）...")
        else:
            self.simulation_thread.pause()
            self.pause_btn.setText("继续")
            self.status_bar.showMessage(f"已暂停（模拟日期：{self.current_sim_date}）")

    def stop_simulation(self):
        if self.simulation_thread:
            self.simulation_thread.stop()
            self.simulation_thread.wait()
        self._set_stopped_state()
        self._generate_report()
        self._save_simulation_result()

    def reset_simulation(self):
        if self.simulation_thread:
            self.simulation_thread.stop()
            self.simulation_thread.wait()
        self.simulation = None
        self.simulation_thread = None
        self.current_sim_date = None
        self.progress_bar.setValue(0)
        self.progress_label.setText("0 / 0 步")
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self.topology_view.reset()
        self.heatmap_view.reset()
        self.realtime_view.reset()
        self.analytics_view.reset()
        self.calendar_view.reset()
        self.status_bar.showMessage("已重置")

    def _set_stopped_state(self):
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("暂停")
        self.stop_btn.setEnabled(False)
        self.reset_btn.setEnabled(True)
        self.status_bar.showMessage("已停止")

    def _on_update(self, step, passenger_count, densities, avg_density, max_queue):
        total = self.progress_bar.maximum()
        self.progress_bar.setValue(step)
        self.progress_label.setText(f"{step} / {total} 步")
        self.status_bar.showMessage(
            f"运行中（模拟日期：{self.current_sim_date}）— 步数: {step}/{total}  "
            f"乘客: {passenger_count}  平均密度: {avg_density:.3f}"
        )
        if not self.simulation:
            return
        graph = self.simulation.station_graph.get_graph()
        passengers = self.simulation.simulation.get_passengers()
        self.topology_view.update_view(graph, passengers)
        self.topology_view.update_congestion(densities)
        self.heatmap_view.update_view(graph, densities)
        self.realtime_view.update_data(step, passenger_count, avg_density, max_queue)

    def _on_finished(self):
        self._set_stopped_state()
        self.status_bar.showMessage(f"仿真完成（模拟日期：{self.current_sim_date}）")
        self._generate_report()
        self._save_simulation_result()
        self.calendar_view.refresh_data()

    def _generate_report(self):
        if self.simulation:
            report = self.simulation.generate_analytics()
            self.analytics_view.update_report(report)
            self.tab_widget.setCurrentIndex(3)

    def _save_simulation_result(self):
        if not self.simulation or not self.current_sim_date:
            return
        global simulation_history
        report = self.simulation.generate_analytics()
        passenger_stats = report.get('passenger_stats', {})
        density_stats = report.get('density_stats', {})
        new_row = {
            "sim_date": self.current_sim_date,
            "station_size": self.station_size_combo.currentText(),
            "total_steps": int(self.steps_edit.text() or 100),
            "total_passengers": passenger_stats.get('passenger_count', 0),
            "avg_density": density_stats.get('average_density', 0),
            "max_density": density_stats.get('max_density', 0),
            "avg_wait_time": passenger_stats.get('average_wait_time', 0),
            "max_queue": max(len(q) for q in self.simulation.simulation.queues.values()) if self.simulation.simulation.queues else 0
        }
        simulation_history = pd.concat([simulation_history, pd.DataFrame([new_row])], ignore_index=True)

# ─────────────────────────────────────────────
#  程序入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(_get_qt_chinese_font(9))
    import os
    _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.exists(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))
    window = SubwaySimulationGUI()
    window.show()
    sys.exit(app.exec_())