import networkx as nx
import json
import pickle


class StationGraph:
    """地铁站拓扑图模型 — 基于有向图，支持多楼层、多出口、多线路"""

    NODE_TYPES = {'entrance', 'exit', 'security', 'ticket', 'gate',
                  'platform', 'corridor', 'stairs', 'escalator', 'waiting_area'}

    def __init__(self):
        self.graph = nx.DiGraph()
        # 缓存：节点按类型、按楼层的索引，避免每次遍历 O(N)
        self._type_index = {}
        self._floor_index = {}
        self._dirty = True

    def add_node(self, node_id, node_type, capacity, x, y,
                 floor=0, area=100.0, base_speed=1.0,
                 service_rate=None, dwell_time=None):
        """添加节点

        Args:
            node_id: 节点唯一标识
            node_type: 节点类型
            capacity: 节点容量（人）
            x, y: 平面坐标
            floor: 楼层（0=地面，-1=地下一层等）
            area: 面积 (m²)
            base_speed: 基础通行速度上限 (m/s)
            service_rate: 服务率 (人/秒)，仅对服务节点有效
            dwell_time: 列车停站时间 (秒)，仅对站台有效
        """
        if node_type not in self.NODE_TYPES:
            raise ValueError(f"未知节点类型: {node_type}")

        self.graph.add_node(
            node_id,
            type=node_type,
            capacity=capacity,
            x=x, y=y,
            floor=floor,
            area=area,
            base_speed=base_speed,
            service_rate=service_rate,
            dwell_time=dwell_time,
            current_density=0.0,
            congestion=1.0,
            passenger_count=0,
        )
        self._dirty = True

    def add_edge(self, from_node, to_node, distance, width,
                 capacity=10, base_time=1.0, congestion_factor=1.0,
                 bidirectional=False):
        """添加边

        Args:
            from_node, to_node: 起止节点
            distance: 通道长度 (m)
            width: 通道宽度 (m)
            capacity: 边容量（人/秒估算）
            base_time: 基础通行时间 (s)
            congestion_factor: 拥堵系数
            bidirectional: 是否双向（自动添加反向边）
        """
        if from_node not in self.graph or to_node not in self.graph:
            raise ValueError(f"节点不存在: {from_node} -> {to_node}")

        self.graph.add_edge(
            from_node, to_node,
            distance=distance,
            width=width,
            capacity=capacity,
            base_time=base_time,
            congestion_factor=congestion_factor,
            current_passengers=0,
        )
        if bidirectional:
            self.graph.add_edge(
                to_node, from_node,
                distance=distance,
                width=width,
                capacity=capacity,
                base_time=base_time,
                congestion_factor=congestion_factor,
                current_passengers=0,
            )
        self._dirty = True

    def get_node(self, node_id):
        if node_id in self.graph.nodes:
            return self.graph.nodes[node_id]
        return None

    def get_edge(self, from_node, to_node):
        if self.graph.has_edge(from_node, to_node):
            return self.graph[from_node][to_node]
        return None

    def update_node_density(self, node_id, density):
        if node_id in self.graph.nodes:
            self.graph.nodes[node_id]['current_density'] = density
            self.graph.nodes[node_id]['congestion'] = self._calculate_congestion(density)

    def update_edge_congestion(self, from_node, to_node, congestion_factor):
        if self.graph.has_edge(from_node, to_node):
            self.graph[from_node][to_node]['congestion_factor'] = max(1.0, congestion_factor)

    @staticmethod
    def _calculate_congestion(density):
        """基于Weidmann模型的连续拥堵系数计算"""
        if density <= 0:
            return 1.0
        # 使用连续函数替代阶梯函数，更平滑
        # congestion = 1 + 0.5 * density^0.8
        return min(5.0, 1.0 + 0.5 * (density ** 0.8))

    def get_neighbors(self, node_id):
        return list(self.graph.neighbors(node_id))

    def get_predecessors(self, node_id):
        return list(self.graph.predecessors(node_id))

    def _rebuild_index(self):
        """重建类型和楼层索引"""
        self._type_index.clear()
        self._floor_index.clear()
        for node, data in self.graph.nodes(data=True):
            nt = data['type']
            nf = data.get('floor', 0)
            self._type_index.setdefault(nt, []).append(node)
            self._floor_index.setdefault(nf, []).append(node)
        self._dirty = False

    def get_nodes_by_type(self, node_type):
        if self._dirty:
            self._rebuild_index()
        return self._type_index.get(node_type, []).copy()

    def get_nodes_by_floor(self, floor):
        if self._dirty:
            self._rebuild_index()
        return self._floor_index.get(floor, []).copy()

    def get_all_floors(self):
        if self._dirty:
            self._rebuild_index()
        return sorted(self._floor_index.keys())

    def get_graph(self):
        return self.graph

    def node_count(self):
        return self.graph.number_of_nodes()

    def edge_count(self):
        return self.graph.number_of_edges()

    # ── 持久化 ──────────────────────────────
    def save_graph(self, filename):
        """保存图结构（使用 pickle，兼容 NetworkX 3.x）"""
        with open(filename, 'wb') as f:
            pickle.dump(self.graph, f)

    def load_graph(self, filename):
        """加载图结构"""
        with open(filename, 'rb') as f:
            self.graph = pickle.load(f)
        self._dirty = True

    def to_json(self):
        """导出为 JSON 格式"""
        data = {
            'nodes': [
                {'id': n, **{k: v for k, v in d.items()
                 if not isinstance(v, (set, dict)) or k == 'type'}}
                for n, d in self.graph.nodes(data=True)
            ],
            'edges': [
                {'from': u, 'to': v, **d}
                for u, v, d in self.graph.edges(data=True)
            ]
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    def from_json(self, json_str):
        """从 JSON 导入"""
        data = json.loads(json_str)
        self.graph.clear()
        for n in data['nodes']:
            nid = n.pop('id')
            self.add_node(nid, **n)
        for e in data['edges']:
            self.add_edge(e.pop('from'), e.pop('to'), **e)
