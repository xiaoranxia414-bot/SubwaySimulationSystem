from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QComboBox, QTextEdit, 
    QTabWidget, QProgressBar, QStatusBar, QFrame, QSplitter,
    QTableWidget, QTableWidgetItem, QGridLayout, QGraphicsScene, 
    QGraphicsView, QGraphicsEllipseItem, QGraphicsLineItem, QDialog,
    QFormLayout, QDoubleSpinBox, QSpinBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPointF
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QBrush, QCursor
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
# 设置matplotlib中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']  # 使用黑体
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
import networkx as nx
import sys
import time
from core import StationGraph, SimulationEngine, PathPlanner, AnalyticsModule

class SimulationThread(QThread):
    """仿真线程"""
    update_signal = pyqtSignal(int, int, dict, float, int)  # 时间步, 乘客数量, 密度数据, 平均密度, 最长队列
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
            
            # 执行仿真步骤
            self.simulation.run_simulation_step()
            
            # 每10步发送更新信号
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
                
                # 计算平均密度
                avg_density = total_density / node_count if node_count > 0 else 0
                
                # 获取最长队列
                for node_id, queue in self.simulation.simulation.queues.items():
                    queue_length = len(queue)
                    if queue_length > max_queue:
                        max_queue = queue_length
                
                # 确保至少有一个队列被检查
                if not self.simulation.simulation.queues:
                    # 如果没有队列，设置为0
                    max_queue = 0
                
                self.update_signal.emit(i + 1, passenger_count, densities, avg_density, max_queue)
            
            # 暂停一下，避免UI卡顿
            time.sleep(0.1)
        
        self.finished_signal.emit()
    
    def pause(self):
        self.paused = True
    
    def resume(self):
        self.paused = False
    
    def stop(self):
        self.running = False
        self.paused = False

class TopologyView(QWidget):
    """拓扑图视图"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # 工具栏
        self.toolbar = QHBoxLayout()
        self.add_node_button = QPushButton("添加节点")
        self.add_edge_button = QPushButton("添加边")
        self.delete_button = QPushButton("删除")
        self.toolbar.addWidget(self.add_node_button)
        self.toolbar.addWidget(self.add_edge_button)
        self.toolbar.addWidget(self.delete_button)
        self.layout.addLayout(self.toolbar)
        
        # 图形场景和视图
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setSceneRect(0, 0, 800, 600)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.layout.addWidget(self.view)
        
        # 状态
        self.add_edge_mode = False
        self.start_node = None
        self.temp_edge = None
        
        # 节点和边的映射
        self.node_items = {}
        self.edge_items = {}
        
        # 信号连接
        self.add_node_button.clicked.connect(self.add_node)
        self.add_edge_button.clicked.connect(self.toggle_add_edge_mode)
        self.delete_button.clicked.connect(self.delete_selected)
        self.view.mousePressEvent = self.mouse_press_event
        self.view.mouseMoveEvent = self.mouse_move_event
        self.view.mouseReleaseEvent = self.mouse_release_event
        self.view.mouseDoubleClickEvent = self.mouse_double_click_event
        
        # 加载默认拓扑图
        self._load_default_topology()
    
    def add_node(self):
        """添加节点"""
        dialog = NodeDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            node_id = data['id']
            if node_id:
                # 在鼠标位置创建节点
                pos = self.view.mapToScene(QCursor.pos() - self.view.mapToGlobal(self.view.pos()))
                node_item = NodeItem(node_id, data['type'], pos.x(), pos.y())
                self.scene.addItem(node_item)
                self.node_items[node_id] = node_item
    
    def toggle_add_edge_mode(self):
        """切换添加边模式"""
        self.add_edge_mode = not self.add_edge_mode
        self.add_edge_button.setText("取消添加边" if self.add_edge_mode else "添加边")
        self.start_node = None
        if self.temp_edge:
            self.scene.removeItem(self.temp_edge)
            self.temp_edge = None
    
    def delete_selected(self):
        """删除选中的项"""
        for item in self.scene.selectedItems():
            if isinstance(item, NodeItem):
                # 删除相关的边
                edges_to_remove = []
                for (from_node, to_node), edge_item in self.edge_items.items():
                    if edge_item.from_node == item or edge_item.to_node == item:
                        edges_to_remove.append((from_node, to_node))
                
                for edge_key in edges_to_remove:
                    if edge_key in self.edge_items:
                        self.scene.removeItem(self.edge_items[edge_key])
                        del self.edge_items[edge_key]
                
                # 删除节点
                del self.node_items[item.node_id]
                self.scene.removeItem(item)
            elif isinstance(item, EdgeItem):
                # 删除边
                for (from_node, to_node), edge_item in self.edge_items.items():
                    if edge_item == item:
                        del self.edge_items[(from_node, to_node)]
                        break
                self.scene.removeItem(item)
    
    def mouse_press_event(self, event):
        """鼠标按下事件"""
        if self.add_edge_mode:
            pos = event.pos()
            item = self.view.itemAt(pos)
            if isinstance(item, NodeItem):
                if not self.start_node:
                    # 选择起点
                    self.start_node = item
                else:
                    # 选择终点
                    if self.start_node != item:
                        # 创建边
                        edge_key = (self.start_node.node_id, item.node_id)
                        if edge_key not in self.edge_items:
                            edge_item = EdgeItem(self.start_node, item)
                            self.scene.addItem(edge_item)
                            self.edge_items[edge_key] = edge_item
                    # 重置
                    self.start_node = None
        else:
            # 调用默认的鼠标事件处理
            QGraphicsView.mousePressEvent(self.view, event)
    
    def mouse_move_event(self, event):
        """鼠标移动事件"""
        if self.add_edge_mode and self.start_node:
            # 绘制临时边
            pos = self.view.mapToScene(event.pos())
            if self.temp_edge:
                self.scene.removeItem(self.temp_edge)
            self.temp_edge = QGraphicsLineItem(self.start_node.x(), self.start_node.y(), pos.x(), pos.y())
            self.temp_edge.setPen(QPen(QColor('gray'), 2, Qt.DashLine))
            self.scene.addItem(self.temp_edge)
        else:
            # 调用默认的鼠标事件处理
            QGraphicsView.mouseMoveEvent(self.view, event)
    
    def mouse_release_event(self, event):
        """鼠标释放事件"""
        if self.add_edge_mode and self.temp_edge:
            self.scene.removeItem(self.temp_edge)
            self.temp_edge = None
        # 调用默认的鼠标事件处理
        QGraphicsView.mouseReleaseEvent(self.view, event)
    
    def mouse_double_click_event(self, event):
        """鼠标双击事件"""
        pos = event.pos()
        item = self.view.itemAt(pos)
        
        if isinstance(item, NodeItem):
            # 双击编辑节点属性
            node_data = {
                'id': item.node_id,
                'type': item.node_type,
                'capacity': 50,  # 默认值
                'area': 100.0,  # 默认值
                'base_speed': 1.0  # 默认值
            }
            dialog = NodeDialog(self, node_data)
            if dialog.exec_() == QDialog.Accepted:
                new_data = dialog.get_data()
                new_node_id = new_data['id']
                
                if new_node_id and new_node_id != item.node_id:
                    # 更新节点ID
                    del self.node_items[item.node_id]
                    item.node_id = new_node_id
                    self.node_items[new_node_id] = item
                
                # 更新节点类型
                if new_data['type'] != item.node_type:
                    item.node_type = new_data['type']
                    item.setBrush(item._get_brush())
        else:
            # 双击添加节点
            dialog = NodeDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                data = dialog.get_data()
                node_id = data['id']
                if node_id:
                    # 在双击位置创建节点
                    scene_pos = self.view.mapToScene(pos)
                    node_item = NodeItem(node_id, data['type'], scene_pos.x(), scene_pos.y())
                    self.scene.addItem(node_item)
                    self.node_items[node_id] = node_item
    
    def update_view(self, graph, passengers):
        """更新拓扑图"""
        # 清空场景
        self.scene.clear()
        self.node_items.clear()
        self.edge_items.clear()
        
        # 添加节点
        pos = {}
        for node, data in graph.nodes(data=True):
            pos[node] = (data['x'], data['y'])
            node_item = NodeItem(node, data['type'], data['x'], data['y'])
            self.scene.addItem(node_item)
            self.node_items[node] = node_item
        
        # 添加边
        for u, v, data in graph.edges(data=True):
            if u in self.node_items and v in self.node_items:
                edge_item = EdgeItem(self.node_items[u], self.node_items[v])
                self.scene.addItem(edge_item)
                self.edge_items[(u, v)] = edge_item
        
        # 统计每个节点的乘客数量
        node_passenger_counts = {}
        for passenger in passengers:
            node_id = passenger.current_node
            if node_id not in node_passenger_counts:
                node_passenger_counts[node_id] = 0
            node_passenger_counts[node_id] += 1
        
        # 更新节点标签
        for node, item in self.node_items.items():
            count = node_passenger_counts.get(node, 0)
            # 更新乘客数量标签
            item.update_passenger_count(count)
    
    def reset(self):
        """重置视图"""
        self.scene.clear()
        self.node_items.clear()
        self.edge_items.clear()
        # 重新加载默认拓扑图
        self._load_default_topology()
    
    def get_graph(self):
        """获取图结构"""
        graph = StationGraph()
        
        # 添加节点
        for node_id, item in self.node_items.items():
            graph.add_node(
                node_id,
                item.node_type,
                50,  # 默认容量
                item.x(),
                item.y(),
                area=100.0,
                base_speed=1.0
            )
        
        # 添加边
        for (from_node, to_node), item in self.edge_items.items():
            # 计算距离
            distance = ((item.from_node.x() - item.to_node.x()) ** 2 + 
                       (item.from_node.y() - item.to_node.y()) ** 2) ** 0.5
            graph.add_edge(from_node, to_node, distance, 2)
        
        return graph
    
    def update_congestion(self, congestion_data):
        """更新拥堵状态"""
        for node_id, congestion in congestion_data.items():
            if node_id in self.node_items:
                self.node_items[node_id].update_congestion(congestion)
        
        for (from_node, to_node), edge_item in self.edge_items.items():
            # 暂时使用默认值
            edge_item.update_congestion(1.0)
    
    def _load_default_topology(self):
        """加载默认拓扑图"""
        # 创建默认的中型站拓扑
        node_count = 2
        
        # 添加入口节点
        for i in range(1, node_count + 1):
            node_id = f'entrance{i}'
            node_item = NodeItem(node_id, 'entrance', 0, 5 * i)
            self.scene.addItem(node_item)
            self.node_items[node_id] = node_item
        
        # 添加售票区节点
        for i in range(1, node_count + 1):
            node_id = f'ticket{i}'
            node_item = NodeItem(node_id, 'ticket', 5, 5 * i)
            self.scene.addItem(node_item)
            self.node_items[node_id] = node_item
        
        # 添加安检区节点
        for i in range(1, node_count + 1):
            node_id = f'security{i}'
            node_item = NodeItem(node_id, 'security', 10, 5 * i)
            self.scene.addItem(node_item)
            self.node_items[node_id] = node_item
        
        # 添加闸机区节点
        for i in range(1, node_count + 1):
            node_id = f'gate{i}'
            node_item = NodeItem(node_id, 'gate', 15, 5 * i)
            self.scene.addItem(node_item)
            self.node_items[node_id] = node_item
        
        # 添加通道节点
        node_id = 'corridor1'
        node_item = NodeItem(node_id, 'corridor', 20, 10)
        self.scene.addItem(node_item)
        self.node_items[node_id] = node_item
        
        # 添加楼梯节点
        for i in range(1, node_count + 1):
            node_id = f'stairs{i}'
            node_item = NodeItem(node_id, 'stairs', 25, 5 * i)
            self.scene.addItem(node_item)
            self.node_items[node_id] = node_item
        
        # 添加扶梯节点
        for i in range(1, node_count + 1):
            node_id = f'escalator{i}'
            node_item = NodeItem(node_id, 'escalator', 25, 5 * i + 2.5)
            self.scene.addItem(node_item)
            self.node_items[node_id] = node_item
        
        # 添加站台节点
        for i in range(1, node_count + 1):
            node_id = f'platform{i}'
            node_item = NodeItem(node_id, 'platform', 30, 5 * i)
            self.scene.addItem(node_item)
            self.node_items[node_id] = node_item
        
        # 添加出口节点
        for i in range(1, node_count + 1):
            node_id = f'exit{i}'
            node_item = NodeItem(node_id, 'exit', 35, 5 * i)
            self.scene.addItem(node_item)
            self.node_items[node_id] = node_item
        
        # 添加边
        # 入口到售票区
        for i in range(1, node_count + 1):
            from_node = f'entrance{i}'
            to_node = f'ticket{i}'
            if from_node in self.node_items and to_node in self.node_items:
                edge_item = EdgeItem(self.node_items[from_node], self.node_items[to_node])
                self.scene.addItem(edge_item)
                self.edge_items[(from_node, to_node)] = edge_item
        
        # 售票区到安检区
        for i in range(1, node_count + 1):
            from_node = f'ticket{i}'
            to_node = f'security{i}'
            if from_node in self.node_items and to_node in self.node_items:
                edge_item = EdgeItem(self.node_items[from_node], self.node_items[to_node])
                self.scene.addItem(edge_item)
                self.edge_items[(from_node, to_node)] = edge_item
        
        # 安检区到闸机区
        for i in range(1, node_count + 1):
            from_node = f'security{i}'
            to_node = f'gate{i}'
            if from_node in self.node_items and to_node in self.node_items:
                edge_item = EdgeItem(self.node_items[from_node], self.node_items[to_node])
                self.scene.addItem(edge_item)
                self.edge_items[(from_node, to_node)] = edge_item
        
        # 闸机区到通道
        for i in range(1, node_count + 1):
            from_node = f'gate{i}'
            to_node = 'corridor1'
            if from_node in self.node_items and to_node in self.node_items:
                edge_item = EdgeItem(self.node_items[from_node], self.node_items[to_node])
                self.scene.addItem(edge_item)
                self.edge_items[(from_node, to_node)] = edge_item
        
        # 通道到楼梯/扶梯
        for i in range(1, node_count + 1):
            from_node = 'corridor1'
            to_node = f'stairs{i}'
            if from_node in self.node_items and to_node in self.node_items:
                edge_item = EdgeItem(self.node_items[from_node], self.node_items[to_node])
                self.scene.addItem(edge_item)
                self.edge_items[(from_node, to_node)] = edge_item
            
            from_node = 'corridor1'
            to_node = f'escalator{i}'
            if from_node in self.node_items and to_node in self.node_items:
                edge_item = EdgeItem(self.node_items[from_node], self.node_items[to_node])
                self.scene.addItem(edge_item)
                self.edge_items[(from_node, to_node)] = edge_item
        
        # 楼梯/扶梯到站台
        for i in range(1, node_count + 1):
            from_node = f'stairs{i}'
            to_node = f'platform{i}'
            if from_node in self.node_items and to_node in self.node_items:
                edge_item = EdgeItem(self.node_items[from_node], self.node_items[to_node])
                self.scene.addItem(edge_item)
                self.edge_items[(from_node, to_node)] = edge_item
            
            from_node = f'escalator{i}'
            to_node = f'platform{i}'
            if from_node in self.node_items and to_node in self.node_items:
                edge_item = EdgeItem(self.node_items[from_node], self.node_items[to_node])
                self.scene.addItem(edge_item)
                self.edge_items[(from_node, to_node)] = edge_item
        
        # 站台到出口
        for i in range(1, node_count + 1):
            from_node = f'platform{i}'
            to_node = f'exit{i}'
            if from_node in self.node_items and to_node in self.node_items:
                edge_item = EdgeItem(self.node_items[from_node], self.node_items[to_node])
                self.scene.addItem(edge_item)
                self.edge_items[(from_node, to_node)] = edge_item

class NodeDialog(QDialog):
    """节点属性对话框"""
    
    def __init__(self, parent=None, node_data=None):
        super().__init__(parent)
        self.setWindowTitle("节点属性")
        self.setGeometry(200, 200, 300, 300)
        
        self.layout = QFormLayout(self)
        
        # 节点ID
        self.id_edit = QLineEdit()
        self.layout.addRow("节点ID:", self.id_edit)
        
        # 节点类型
        self.type_combo = QComboBox()
        self.type_combo.addItems(['entrance', 'exit', 'security', 'ticket', 'gate', 'platform', 'corridor', 'stairs', 'escalator'])
        self.layout.addRow("节点类型:", self.type_combo)
        
        # 容量
        self.capacity_spin = QSpinBox()
        self.capacity_spin.setRange(1, 1000)
        self.capacity_spin.setValue(50)
        self.layout.addRow("容量:", self.capacity_spin)
        
        # 面积
        self.area_spin = QDoubleSpinBox()
        self.area_spin.setRange(10.0, 1000.0)
        self.area_spin.setValue(100.0)
        self.layout.addRow("面积:", self.area_spin)
        
        # 基础速度
        self.base_speed_spin = QDoubleSpinBox()
        self.base_speed_spin.setRange(0.1, 2.0)
        self.base_speed_spin.setValue(1.0)
        self.layout.addRow("基础速度:", self.base_speed_spin)
        
        # 按钮
        self.button_layout = QHBoxLayout()
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        self.button_layout.addWidget(self.ok_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addRow(self.button_layout)
        
        # 信号连接
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        # 填充数据
        if node_data:
            self.id_edit.setText(node_data.get('id', ''))
            # 直接设置节点类型，不进行条件判断
            self.type_combo.setCurrentText(node_data.get('type', 'entrance'))
            self.capacity_spin.setValue(node_data.get('capacity', 50))
            self.area_spin.setValue(node_data.get('area', 100.0))
            self.base_speed_spin.setValue(node_data.get('base_speed', 1.0))
    
    def get_data(self):
        """获取节点数据"""
        return {
            'id': self.id_edit.text(),
            'type': self.type_combo.currentText(),
            'capacity': self.capacity_spin.value(),
            'area': self.area_spin.value(),
            'base_speed': self.base_speed_spin.value()
        }

from PyQt5.QtWidgets import QGraphicsTextItem

class NodeItem(QGraphicsEllipseItem):
    """节点图形项"""
    
    def __init__(self, node_id, node_type, x, y, parent=None):
        super().__init__(-10, -10, 20, 20, parent)
        self.node_id = node_id
        self.node_type = node_type
        self.setPos(x, y)
        self.setBrush(self._get_brush())
        self.setPen(QPen(QColor('black'), 2))
        self.setFlag(QGraphicsEllipseItem.ItemIsMovable)
        self.setFlag(QGraphicsEllipseItem.ItemIsSelectable)
        
        # 添加节点ID标签
        self.id_text = QGraphicsTextItem(node_id, self)
        self.id_text.setPos(-15, -30)
        self.id_text.setDefaultTextColor(QColor('black'))
        
        # 添加人数标签
        self.count_text = QGraphicsTextItem("0人", self)
        self.count_text.setPos(-10, 15)
        self.count_text.setDefaultTextColor(QColor('black'))
    
    def _get_brush(self):
        """根据节点类型获取颜色"""
        color_map = {
            'entrance': QColor('green'),
            'exit': QColor('red'),
            'security': QColor('yellow'),
            'ticket': QColor('blue'),
            'gate': QColor('orange'),
            'platform': QColor('purple'),
            'corridor': QColor('gray'),
            'stairs': QColor('brown'),
            'escalator': QColor('pink')
        }
        return QBrush(color_map.get(self.node_type, QColor('white')))
    
    def update_congestion(self, congestion):
        """根据拥堵程度更新颜色"""
        base_brush = self._get_brush()
        base_color = base_brush.color()
        # 向红色渐变
        red_component = min(255, base_color.red() + int(congestion * 50))
        green_component = max(0, base_color.green() - int(congestion * 50))
        blue_component = max(0, base_color.blue() - int(congestion * 50))
        new_color = QColor(red_component, green_component, blue_component)
        self.setBrush(QBrush(new_color))
    
    def update_passenger_count(self, count):
        """更新乘客数量标签"""
        self.count_text.setText(f"{count}人")
    
    def itemChange(self, change, value):
        """处理项目变化"""
        if change == QGraphicsEllipseItem.ItemPositionChange:
            # 当节点位置变化时，更新相关的边
            for edge in self.scene().items():
                if isinstance(edge, EdgeItem):
                    if edge.from_node == self or edge.to_node == self:
                        edge.update_position()
        return super().itemChange(change, value)

class EdgeItem(QGraphicsLineItem):
    """边图形项"""
    
    def __init__(self, from_node, to_node, parent=None):
        super().__init__(parent)
        self.from_node = from_node
        self.to_node = to_node
        self.update_position()
        self.setPen(QPen(QColor('black'), 2))
    
    def update_position(self):
        """更新边的位置"""
        if self.from_node and self.to_node:
            self.setLine(self.from_node.x(), self.from_node.y(), self.to_node.x(), self.to_node.y())
    
    def update_congestion(self, congestion_factor):
        """根据拥堵系数更新颜色和粗细"""
        # 计算粗细
        width = max(2, min(8, 2 + congestion_factor * 2))
        # 计算颜色（向红色渐变）
        red = min(255, int(congestion_factor * 50))
        color = QColor(red, 0, 0)
        self.setPen(QPen(color, width))

class TopologyEditView(QWidget):
    """拓扑编辑视图"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # 工具栏
        self.toolbar = QHBoxLayout()
        self.add_node_button = QPushButton("添加节点")
        self.add_edge_button = QPushButton("添加边")
        self.delete_button = QPushButton("删除")
        self.save_button = QPushButton("保存")
        self.load_button = QPushButton("加载")
        
        self.toolbar.addWidget(self.add_node_button)
        self.toolbar.addWidget(self.add_edge_button)
        self.toolbar.addWidget(self.delete_button)
        self.toolbar.addWidget(self.save_button)
        self.toolbar.addWidget(self.load_button)
        
        self.layout.addLayout(self.toolbar)
        
        # 图形场景和视图
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setSceneRect(0, 0, 800, 600)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        
        self.layout.addWidget(self.view)
        
        # 状态
        self.add_edge_mode = False
        self.start_node = None
        self.temp_edge = None
        
        # 节点和边的映射
        self.node_items = {}
        self.edge_items = {}
        
        # 信号连接
        self.add_node_button.clicked.connect(self.add_node)
        self.add_edge_button.clicked.connect(self.toggle_add_edge_mode)
        self.delete_button.clicked.connect(self.delete_selected)
        self.view.mousePressEvent = self.mouse_press_event
        self.view.mouseMoveEvent = self.mouse_move_event
        self.view.mouseReleaseEvent = self.mouse_release_event
        self.view.mouseDoubleClickEvent = self.mouse_double_click_event
    
    def add_node(self):
        """添加节点"""
        dialog = NodeDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            node_id = data['id']
            if node_id:
                # 在鼠标位置创建节点
                pos = self.view.mapToScene(QCursor.pos() - self.view.mapToGlobal(self.view.pos()))
                node_item = NodeItem(node_id, data['type'], pos.x(), pos.y())
                self.scene.addItem(node_item)
                self.node_items[node_id] = node_item
    
    def toggle_add_edge_mode(self):
        """切换添加边模式"""
        self.add_edge_mode = not self.add_edge_mode
        self.add_edge_button.setText("取消添加边" if self.add_edge_mode else "添加边")
        self.start_node = None
        if self.temp_edge:
            self.scene.removeItem(self.temp_edge)
            self.temp_edge = None
    
    def delete_selected(self):
        """删除选中的项"""
        for item in self.scene.selectedItems():
            if isinstance(item, NodeItem):
                # 删除相关的边
                edges_to_remove = []
                for (from_node, to_node), edge_item in self.edge_items.items():
                    if edge_item.from_node == item or edge_item.to_node == item:
                        edges_to_remove.append((from_node, to_node))
                
                for edge_key in edges_to_remove:
                    if edge_key in self.edge_items:
                        self.scene.removeItem(self.edge_items[edge_key])
                        del self.edge_items[edge_key]
                
                # 删除节点
                del self.node_items[item.node_id]
                self.scene.removeItem(item)
            elif isinstance(item, EdgeItem):
                # 删除边
                for (from_node, to_node), edge_item in self.edge_items.items():
                    if edge_item == item:
                        del self.edge_items[(from_node, to_node)]
                        break
                self.scene.removeItem(item)
    
    def mouse_press_event(self, event):
        """鼠标按下事件"""
        if self.add_edge_mode:
            pos = event.pos()
            item = self.view.itemAt(pos)
            if isinstance(item, NodeItem):
                if not self.start_node:
                    # 选择起点
                    self.start_node = item
                else:
                    # 选择终点
                    if self.start_node != item:
                        # 创建边
                        edge_key = (self.start_node.node_id, item.node_id)
                        if edge_key not in self.edge_items:
                            edge_item = EdgeItem(self.start_node, item)
                            self.scene.addItem(edge_item)
                            self.edge_items[edge_key] = edge_item
                    # 重置
                    self.start_node = None
        else:
            # 调用默认的鼠标事件处理
            QGraphicsView.mousePressEvent(self.view, event)
    
    def mouse_move_event(self, event):
        """鼠标移动事件"""
        if self.add_edge_mode and self.start_node:
            # 绘制临时边
            pos = self.view.mapToScene(event.pos())
            if self.temp_edge:
                self.scene.removeItem(self.temp_edge)
            self.temp_edge = QGraphicsLineItem(self.start_node.x(), self.start_node.y(), pos.x(), pos.y())
            self.temp_edge.setPen(QPen(QColor('gray'), 2, Qt.DashLine))
            self.scene.addItem(self.temp_edge)
        else:
            # 调用默认的鼠标事件处理
            QGraphicsView.mouseMoveEvent(self.view, event)
    
    def mouse_release_event(self, event):
        """鼠标释放事件"""
        if self.add_edge_mode and self.temp_edge:
            self.scene.removeItem(self.temp_edge)
            self.temp_edge = None
        # 调用默认的鼠标事件处理
        QGraphicsView.mouseReleaseEvent(self.view, event)
    
    def mouse_double_click_event(self, event):
        """鼠标双击事件"""
        pos = event.pos()
        item = self.view.itemAt(pos)
        
        if isinstance(item, NodeItem):
            # 双击编辑节点属性
            node_data = {
                'id': item.node_id,
                'type': item.node_type,
                'capacity': 50,  # 默认值
                'area': 100.0,  # 默认值
                'base_speed': 1.0  # 默认值
            }
            dialog = NodeDialog(self, node_data)
            if dialog.exec_() == QDialog.Accepted:
                new_data = dialog.get_data()
                new_node_id = new_data['id']
                
                if new_node_id and new_node_id != item.node_id:
                    # 更新节点ID
                    del self.node_items[item.node_id]
                    item.node_id = new_node_id
                    self.node_items[new_node_id] = item
                
                # 更新节点类型
                if new_data['type'] != item.node_type:
                    item.node_type = new_data['type']
                    item.setBrush(item._get_brush())
        else:
            # 双击添加节点
            dialog = NodeDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                data = dialog.get_data()
                node_id = data['id']
                if node_id:
                    # 在双击位置创建节点
                    scene_pos = self.view.mapToScene(pos)
                    node_item = NodeItem(node_id, data['type'], scene_pos.x(), scene_pos.y())
                    self.scene.addItem(node_item)
                    self.node_items[node_id] = node_item
    
    def update_congestion(self, congestion_data):
        """更新拥堵状态"""
        for node_id, congestion in congestion_data.items():
            if node_id in self.node_items:
                self.node_items[node_id].update_congestion(congestion)
        
        for (from_node, to_node), edge_item in self.edge_items.items():
            # 这里需要获取边的拥堵系数数据
            # 暂时使用默认值
            edge_item.update_congestion(1.0)
    
    def get_graph(self):
        """获取图结构"""
        graph = StationGraph()
        
        # 添加节点
        for node_id, item in self.node_items.items():
            # 这里需要获取节点的完整属性
            graph.add_node(
                node_id,
                item.node_type,
                50,  # 默认容量
                item.x(),
                item.y(),
                area=100.0,
                base_speed=1.0
            )
        
        # 添加边
        for (from_node, to_node), item in self.edge_items.items():
            # 计算距离
            distance = ((item.from_node.x() - item.to_node.x()) ** 2 + 
                       (item.from_node.y() - item.to_node.y()) ** 2) ** 0.5
            graph.add_edge(from_node, to_node, distance, 2)
        
        return graph

class HeatmapView(FigureCanvas):
    """热力图视图"""
    
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(8, 6), dpi=100)
        super().__init__(self.fig)
        self.setParent(parent)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("密度热力图")
        self.ax.text(0.5, 0.5, "请先开始仿真", ha='center', va='center')
        self.draw()
    
    def update_view(self, graph, densities):
        """更新热力图"""
        self.fig.clear()
        self.ax = self.fig.add_subplot(111)
        
        # 获取节点坐标
        node_coords = {}
        for node, data in graph.nodes(data=True):
            node_coords[node] = (data['x'], data['y'])
        
        # 绘制热力图
        if node_coords:
            x_coords = [x for x, y in node_coords.values()]
            y_coords = [y for x, y in node_coords.values()]
            density_values = [densities.get(node, 0) for node in node_coords.keys()]
            
            # 绘制散点图，颜色表示密度
            scatter = self.ax.scatter(x_coords, y_coords, c=density_values, cmap='hot', s=100, alpha=0.7)
            
            # 添加颜色条
            self.fig.colorbar(scatter, ax=self.ax, label='密度')
            
            # 添加节点标签
            for node, (x, y) in node_coords.items():
                self.ax.text(x, y, node, ha='center', va='center', fontsize=8, color='black')
        
        self.ax.set_title("密度热力图")
        self.draw()
    
    def reset(self):
        """重置视图"""
        self.fig.clear()
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("密度热力图")
        self.ax.text(0.5, 0.5, "请先开始仿真", ha='center', va='center')
        self.draw()

class RealtimeDataView(QWidget):
    """实时数据视图"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # 使用matplotlib创建图表
        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("实时数据监控")
        self.ax.set_xlabel("时间 (秒)")
        self.ax.set_ylabel("数值")
        self.ax.grid(True)
        
        self.layout.addWidget(self.canvas)
        
        # 数据存储
        self.time_data = []
        self.passenger_data = []
        self.density_data = []
        self.queue_data = []
        
        # 绘制线条
        self.passenger_line, = self.ax.plot([], [], 'b-', label='乘客数量')
        self.density_line, = self.ax.plot([], [], 'g-', label='平均密度')
        self.queue_line, = self.ax.plot([], [], 'r-', label='最长队列')
        
        # 添加图例
        self.ax.legend()
    
    def update_data(self, time, passenger_count, avg_density=0, max_queue=0):
        """更新数据"""
        self.time_data.append(time)
        self.passenger_data.append(passenger_count)
        self.density_data.append(avg_density)
        self.queue_data.append(max_queue)
        
        # 只显示最近50个数据点
        if len(self.time_data) > 50:
            self.time_data = self.time_data[-50:]
            self.passenger_data = self.passenger_data[-50:]
            self.density_data = self.density_data[-50:]
            self.queue_data = self.queue_data[-50:]
        
        # 更新图表
        self.passenger_line.set_data(self.time_data, self.passenger_data)
        self.density_line.set_data(self.time_data, self.density_data)
        self.queue_line.set_data(self.time_data, self.queue_data)
        
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()
    
    def reset(self):
        """重置视图"""
        self.time_data = []
        self.passenger_data = []
        self.density_data = []
        self.queue_data = []
        
        self.passenger_line.set_data([], [])
        self.density_line.set_data([], [])
        self.queue_line.set_data([], [])
        
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()

class AnalyticsView(QWidget):
    """分析报告视图"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # 创建文本编辑框
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText("分析报告将在此显示...")
        
        self.layout.addWidget(self.text_edit)
    
    def update_report(self, report):
        """更新分析报告"""
        text = "分析报告\n"
        text += "====================\n\n"
        
        if report['passenger_stats']:
            text += "乘客统计:\n"
            text += f"平均等待时间: {report['passenger_stats']['average_wait_time']:.2f}秒\n"
            text += f"最大等待时间: {report['passenger_stats']['max_wait_time']:.2f}秒\n"
            text += f"最小等待时间: {report['passenger_stats']['min_wait_time']:.2f}秒\n"
            text += f"乘客数量: {report['passenger_stats']['passenger_count']}\n"
            text += f"状态分布: {report['passenger_stats']['state_distribution']}\n\n"
        
        if report['density_stats']:
            text += "密度统计:\n"
            text += f"平均密度: {report['density_stats']['average_density']:.2f}\n"
            text += f"最大密度: {report['density_stats']['max_density']:.2f}\n"
            text += f"最小密度: {report['density_stats']['min_density']:.2f}\n"
            text += f"拥堵节点: {report['density_stats']['congested_nodes']}\n\n"
        
        if report['bottlenecks']:
            text += "瓶颈节点:\n"
            text += f"{report['bottlenecks']}\n\n"
        
        if report['top_congested_nodes']:
            text += "最拥堵节点:\n"
            text += f"{report['top_congested_nodes']}\n\n"
        
        if report['visit_counts']:
            text += "累计访问量:\n"
            sorted_visits = sorted(report['visit_counts'].items(), key=lambda x: x[1], reverse=True)
            for node, count in sorted_visits[:10]:  # 显示前10个
                text += f"{node}: {count}\n"
        
        self.text_edit.setPlainText(text)
    
    def reset(self):
        """重置视图"""
        self.text_edit.setPlainText("分析报告将在此显示...")

class SubwaySimulationGUI(QMainWindow):
    """地铁站人流仿真系统GUI"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("地铁站人流仿真系统")
        self.setGeometry(100, 100, 1200, 800)
        
        # 设置中文字体
        font = QFont("SimHei", 9)
        QApplication.setFont(font)
        
        # 创建仿真系统
        self.simulation = None
        self.simulation_thread = None
        
        # 创建中心部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 创建主布局
        self.main_layout = QHBoxLayout(self.central_widget)
        
        # 创建左侧控制面板
        self.control_panel = QWidget()
        self.control_layout = QVBoxLayout(self.control_panel)
        self.control_layout.setContentsMargins(10, 10, 10, 10)
        
        # 仿真控制
        self.control_group = QFrame()
        self.control_group.setFrameShape(QFrame.Box)
        self.control_group.setFrameShadow(QFrame.Sunken)
        self.control_group_layout = QVBoxLayout(self.control_group)
        self.control_group_layout.setContentsMargins(10, 10, 10, 10)
        
        self.control_group_layout.addWidget(QLabel("仿真控制"))
        
        # 控制按钮
        self.button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("开始仿真")
        self.start_button.clicked.connect(self.start_simulation)
        self.button_layout.addWidget(self.start_button)
        
        self.pause_button = QPushButton("暂停仿真")
        self.pause_button.clicked.connect(self.pause_simulation)
        self.pause_button.setEnabled(False)
        self.button_layout.addWidget(self.pause_button)
        
        self.stop_button = QPushButton("停止仿真")
        self.stop_button.clicked.connect(self.stop_simulation)
        self.stop_button.setEnabled(False)
        self.button_layout.addWidget(self.stop_button)
        
        self.reset_button = QPushButton("重置仿真")
        self.reset_button.clicked.connect(self.reset_simulation)
        self.reset_button.setEnabled(False)
        self.button_layout.addWidget(self.reset_button)
        
        self.control_group_layout.addLayout(self.button_layout)
        
        # 仿真参数
        self.params_group = QFrame()
        self.params_group.setFrameShape(QFrame.Box)
        self.params_group.setFrameShadow(QFrame.Sunken)
        self.params_group_layout = QVBoxLayout(self.params_group)
        self.params_group_layout.setContentsMargins(10, 10, 10, 10)
        
        self.params_group_layout.addWidget(QLabel("仿真参数"))
        
        # 仿真步数
        self.steps_layout = QHBoxLayout()
        self.steps_layout.addWidget(QLabel("仿真步数:"))
        self.steps_edit = QLineEdit("100")
        self.steps_layout.addWidget(self.steps_edit)
        self.params_group_layout.addLayout(self.steps_layout)
        
        # 高峰期乘客生成速率
        self.peak_rate_layout = QHBoxLayout()
        self.peak_rate_layout.addWidget(QLabel("高峰期乘客生成速率:"))
        self.peak_rate_edit = QLineEdit("10")
        self.peak_rate_layout.addWidget(self.peak_rate_edit)
        self.params_group_layout.addLayout(self.peak_rate_layout)
        
        # 平峰期乘客生成速率
        self.normal_rate_layout = QHBoxLayout()
        self.normal_rate_layout.addWidget(QLabel("平峰期乘客生成速率:"))
        self.normal_rate_edit = QLineEdit("5")
        self.normal_rate_layout.addWidget(self.normal_rate_edit)
        self.params_group_layout.addLayout(self.normal_rate_layout)
        
        # 路径规划模式
        self.path_mode_layout = QHBoxLayout()
        self.path_mode_layout.addWidget(QLabel("路径规划模式:"))
        self.path_mode_combo = QComboBox()
        self.path_mode_combo.addItems(["最短时间", "最短距离", "多目标优化", "最少区域切换"])
        self.path_mode_layout.addWidget(self.path_mode_combo)
        self.params_group_layout.addLayout(self.path_mode_layout)
        
        # 站点规模
        self.station_size_layout = QHBoxLayout()
        self.station_size_layout.addWidget(QLabel("站点规模:"))
        self.station_size_combo = QComboBox()
        self.station_size_combo.addItems(["小型站", "中型站", "大型站"])
        self.station_size_layout.addWidget(self.station_size_combo)
        self.params_group_layout.addLayout(self.station_size_layout)
        
        # 运营时间段
        self.operation_time_layout = QHBoxLayout()
        self.operation_time_layout.addWidget(QLabel("运营时间段:"))
        self.operation_time_edit = QLineEdit("7-9,17-19")
        self.operation_time_edit.setToolTip("格式: 开始1-结束1,开始2-结束2")
        self.operation_time_layout.addWidget(self.operation_time_edit)
        self.params_group_layout.addLayout(self.operation_time_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.params_group_layout.addWidget(self.progress_bar)
        
        # 添加到控制面板
        self.control_layout.addWidget(self.control_group)
        self.control_layout.addWidget(self.params_group)
        self.control_layout.addStretch()
        
        # 创建右侧主显示区域
        self.main_display = QWidget()
        self.main_display_layout = QVBoxLayout(self.main_display)
        
        # 选项卡
        self.tab_widget = QTabWidget()
        
        # 拓扑图选项卡
        self.topology_tab = QWidget()
        self.topology_layout = QVBoxLayout(self.topology_tab)
        self.topology_view = TopologyView()
        self.topology_layout.addWidget(self.topology_view)
        self.tab_widget.addTab(self.topology_tab, "拓扑图")
        
        # 热力图选项卡
        self.heatmap_tab = QWidget()
        self.heatmap_layout = QVBoxLayout(self.heatmap_tab)
        self.heatmap_view = HeatmapView()
        self.heatmap_layout.addWidget(self.heatmap_view)
        self.tab_widget.addTab(self.heatmap_tab, "热力图")
        
        # 实时数据选项卡
        self.realtime_tab = QWidget()
        self.realtime_layout = QVBoxLayout(self.realtime_tab)
        self.realtime_view = RealtimeDataView()
        self.realtime_layout.addWidget(self.realtime_view)
        self.tab_widget.addTab(self.realtime_tab, "实时数据")
        
        # 分析报告选项卡
        self.analytics_tab = QWidget()
        self.analytics_layout = QVBoxLayout(self.analytics_tab)
        self.analytics_view = AnalyticsView()
        self.analytics_layout.addWidget(self.analytics_view)
        self.tab_widget.addTab(self.analytics_tab, "分析报告")
        
        self.main_display_layout.addWidget(self.tab_widget)
        
        # 添加到主布局
        self.main_layout.addWidget(self.control_panel, 1)
        self.main_layout.addWidget(self.main_display, 4)
        
        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
    
    def start_simulation(self):
        """开始仿真"""
        # 更新状态
        self.status_bar.showMessage("运行中")
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.reset_button.setEnabled(True)
        
        # 获取站点规模和运营时间段
        station_size = self.station_size_combo.currentText()
        operation_time = self.operation_time_edit.text()
        
        # 获取拓扑图视图中的图结构
        graph = self.topology_view.get_graph()
        
        # 创建仿真系统
        self.simulation = SubwaySimulation(station_size=station_size, operation_time=operation_time, custom_graph=graph)
        
        # 获取仿真步数
        steps = int(self.steps_edit.text())
        self.progress_bar.setRange(0, steps)
        self.progress_bar.setValue(0)
        
        # 启动仿真线程
        self.simulation_thread = SimulationThread(self.simulation, steps)
        self.simulation_thread.update_signal.connect(self.update_simulation)
        self.simulation_thread.finished_signal.connect(self.simulation_finished)
        self.simulation_thread.start()
    
    def pause_simulation(self):
        """暂停仿真"""
        if self.simulation_thread:
            if self.simulation_thread.paused:
                self.simulation_thread.resume()
                self.status_bar.showMessage("运行中")
                self.pause_button.setText("暂停仿真")
            else:
                self.simulation_thread.pause()
                self.status_bar.showMessage("暂停")
                self.pause_button.setText("继续仿真")
    
    def stop_simulation(self):
        """停止仿真"""
        if self.simulation_thread:
            self.simulation_thread.stop()
            self.simulation_thread.wait()
        
        self.status_bar.showMessage("已停止")
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("暂停仿真")
        self.stop_button.setEnabled(False)
        self.reset_button.setEnabled(True)
        
        # 生成分析报告
        self.generate_report()
    
    def reset_simulation(self):
        """重置仿真"""
        if self.simulation_thread:
            self.simulation_thread.stop()
            self.simulation_thread.wait()
        
        self.status_bar.showMessage("就绪")
        self.simulation = None
        self.simulation_thread = None
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("暂停仿真")
        self.stop_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        self.progress_bar.setValue(0)
        
        # 重置可视化
        self.topology_view.reset()
        self.heatmap_view.reset()
        self.realtime_view.reset()
        self.analytics_view.reset()
    
    def update_simulation(self, step, passenger_count, densities, avg_density=0, max_queue=0):
        """更新仿真状态"""
        # 更新进度条
        self.progress_bar.setValue(step)
        self.status_bar.showMessage(f"运行中 - 步数: {step}/{self.progress_bar.maximum()}")
        
        # 更新拓扑图
        if self.simulation:
            graph = self.simulation.station_graph.get_graph()
            passengers = self.simulation.simulation.get_passengers()
            self.topology_view.update_view(graph, passengers)
            
            # 更新热力图
            self.heatmap_view.update_view(graph, densities)
            
            # 更新实时数据
            self.realtime_view.update_data(step, passenger_count, avg_density, max_queue)
            
            # 更新拓扑图视图的拥堵状态
            congestion_data = {}
            for node_id, density in densities.items():
                congestion_data[node_id] = density
            self.topology_view.update_congestion(congestion_data)
    
    def simulation_finished(self):
        """仿真结束"""
        self.status_bar.showMessage("已完成")
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("暂停仿真")
        self.stop_button.setEnabled(False)
        self.reset_button.setEnabled(True)
        
        # 生成分析报告
        self.generate_report()
    
    def generate_report(self):
        """生成分析报告"""
        if self.simulation:
            report = self.simulation.generate_analytics()
            self.analytics_view.update_report(report)
            # 生成热力图
            self.simulation.analytics.plot_heatmap()

class SubwaySimulation:
    """地铁站人流仿真系统"""
    
    def __init__(self, station_size="中型站", operation_time="7-9,17-19", custom_graph=None):
        """初始化仿真系统
        
        Args:
            station_size: 站点规模 (小型站, 中型站, 大型站)
            operation_time: 运营时间段，格式: "开始1-结束1,开始2-结束2"
            custom_graph: 自定义图结构
        """
        # 创建地铁站图
        self.station_size = station_size
        self.operation_time = operation_time
        self.peak_hours = self._parse_operation_time(operation_time)
        
        # 使用自定义图结构或创建默认图
        if custom_graph:
            self.station_graph = custom_graph
        else:
            self.station_graph = self._create_station_graph()
        
        # 创建路径规划器
        self.path_planner = PathPlanner(self.station_graph)
        # 创建仿真引擎
        self.simulation = SimulationEngine(self.station_graph, self.path_planner, self.peak_hours)
        # 创建分析模块
        self.analytics = AnalyticsModule(self.station_graph)
    
    def _parse_operation_time(self, operation_time):
        """解析运营时间段
        
        Args:
            operation_time: 运营时间段字符串
        
        Returns:
            list: 高峰期时间段列表 [(start1, end1), (start2, end2), ...]
        """
        peak_hours = []
        try:
            periods = operation_time.split(',')
            for period in periods:
                start_end = period.split('-')
                if len(start_end) == 2:
                    start = int(start_end[0].strip())
                    end = int(start_end[1].strip())
                    peak_hours.append((start, end))
        except:
            # 默认高峰期
            peak_hours = [(7, 9), (17, 19)]
        return peak_hours
    
    def _create_station_graph(self):
        """创建地铁站拓扑图"""
        graph = StationGraph()
        
        # 根据站点规模调整参数
        if self.station_size == "小型站":
            entrance_capacity = 30
            ticket_capacity = 20
            security_capacity = 15
            gate_capacity = 10
            corridor_capacity = 80
            platform_capacity = 150
            exit_capacity = 30
            node_count = 1
        elif self.station_size == "中型站":
            entrance_capacity = 50
            ticket_capacity = 30
            security_capacity = 20
            gate_capacity = 15
            corridor_capacity = 100
            platform_capacity = 200
            exit_capacity = 50
            node_count = 2
        else:  # 大型站
            entrance_capacity = 80
            ticket_capacity = 50
            security_capacity = 30
            gate_capacity = 25
            corridor_capacity = 150
            platform_capacity = 300
            exit_capacity = 80
            node_count = 3
        
        # 添加节点
        # 入口
        for i in range(1, node_count + 1):
            graph.add_node(f'entrance{i}', 'entrance', entrance_capacity, 0, 5 * i, area=100.0, base_speed=1.0)
        
        # 售票区
        for i in range(1, node_count + 1):
            graph.add_node(f'ticket{i}', 'ticket', ticket_capacity, 5, 5 * i, area=80.0, base_speed=0.8)
        
        # 安检区
        for i in range(1, node_count + 1):
            graph.add_node(f'security{i}', 'security', security_capacity, 10, 5 * i, area=60.0, base_speed=0.6)
        
        # 闸机区
        for i in range(1, node_count + 1):
            graph.add_node(f'gate{i}', 'gate', gate_capacity, 15, 5 * i, area=40.0, base_speed=1.0)
        
        # 通道
        graph.add_node('corridor1', 'corridor', corridor_capacity, 20, 10, area=200.0, base_speed=1.2)
        
        # 楼梯/扶梯
        for i in range(1, node_count + 1):
            graph.add_node(f'stairs{i}', 'stairs', 10, 25, 5 * i, area=30.0, base_speed=0.5)
            graph.add_node(f'escalator{i}', 'escalator', 20, 25, 5 * i + 2.5, area=50.0, base_speed=0.8)
        
        # 站台
        for i in range(1, node_count + 1):
            graph.add_node(f'platform{i}', 'platform', platform_capacity, 30, 5 * i, area=400.0, base_speed=1.0)
        
        # 出口
        for i in range(1, node_count + 1):
            graph.add_node(f'exit{i}', 'exit', exit_capacity, 35, 5 * i, area=100.0, base_speed=1.0)
        
        # 添加边
        # 入口到售票区
        for i in range(1, node_count + 1):
            graph.add_edge(f'entrance{i}', f'ticket{i}', 5, 2, capacity=10, base_time=1.0)
        
        # 售票区到安检区
        for i in range(1, node_count + 1):
            graph.add_edge(f'ticket{i}', f'security{i}', 5, 2, capacity=8, base_time=1.0)
        
        # 安检区到闸机区
        for i in range(1, node_count + 1):
            graph.add_edge(f'security{i}', f'gate{i}', 5, 2, capacity=5, base_time=1.0)
        
        # 闸机区到通道
        for i in range(1, node_count + 1):
            graph.add_edge(f'gate{i}', 'corridor1', 5, 3, capacity=15, base_time=1.0)
        
        # 通道到楼梯/扶梯
        for i in range(1, node_count + 1):
            graph.add_edge('corridor1', f'stairs{i}', 5, 2, capacity=8, base_time=1.0)
            graph.add_edge('corridor1', f'escalator{i}', 5, 3, capacity=12, base_time=1.0)
        
        # 楼梯/扶梯到站台
        for i in range(1, node_count + 1):
            graph.add_edge(f'stairs{i}', f'platform{i}', 10, 2, capacity=6, base_time=2.0)
            graph.add_edge(f'escalator{i}', f'platform{i}', 10, 3, capacity=10, base_time=1.5)
        
        # 站台到出口
        for i in range(1, node_count + 1):
            graph.add_edge(f'platform{i}', f'exit{i}', 5, 2, capacity=10, base_time=1.0)
        
        return graph
    
    def run_simulation_step(self):
        """运行一个仿真步骤"""
        self.simulation.step()
    
    def generate_analytics(self):
        """生成分析报告"""
        # 收集数据
        passengers = self.simulation.get_passengers()
        densities = {}
        for node in self.station_graph.get_graph().nodes():
            node_info = self.station_graph.get_node(node)
            if node_info:
                densities[node] = node_info.get('current_density', 0)
        
        self.analytics.record_data(self.simulation.get_current_time(), passengers, densities)
        
        # 生成报告
        return self.analytics.generate_report()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 设置应用程序字体
    font = QFont("SimHei", 9)
    app.setFont(font)
    window = SubwaySimulationGUI()
    window.show()
    sys.exit(app.exec_())