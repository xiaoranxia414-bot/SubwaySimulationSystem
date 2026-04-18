import networkx as nx

class StationGraph:
    """地铁站拓扑图模型"""
    
    def __init__(self):
        """初始化地铁站拓扑图"""
        self.graph = nx.DiGraph()
    
    def add_node(self, node_id, node_type, capacity, x, y, floor=0, area=100.0, base_speed=1.0):
        """添加节点
        
        Args:
            node_id: 节点ID
            node_type: 节点类型（安检区、售票区、闸机区、站台等）
            capacity: 节点容量
            x, y: 节点坐标
            floor: 楼层
            area: 节点面积
            base_speed: 基础通行速度上限
        """
        self.graph.add_node(node_id, 
                          type=node_type, 
                          capacity=capacity, 
                          x=x, 
                          y=y, 
                          floor=floor,
                          area=area,
                          base_speed=base_speed,
                          current_density=0,
                          congestion=1.0)
    
    def add_edge(self, from_node, to_node, distance, width, capacity=10, base_time=1.0, congestion_factor=1.0):
        """添加边
        
        Args:
            from_node: 起始节点
            to_node: 目标节点
            distance: 距离
            width: 宽度
            capacity: 边容量
            base_time: 基础通行时间
            congestion_factor: 拥堵系数
        """
        self.graph.add_edge(from_node, to_node, 
                          distance=distance, 
                          width=width, 
                          capacity=capacity,
                          base_time=base_time,
                          congestion_factor=congestion_factor)
    
    def get_node(self, node_id):
        """获取节点信息"""
        if node_id in self.graph.nodes:
            return self.graph.nodes[node_id]
        return None
    
    def get_edge(self, from_node, to_node):
        """获取边信息"""
        if self.graph.has_edge(from_node, to_node):
            return self.graph[from_node][to_node]
        return None
    
    def update_node_density(self, node_id, density):
        """更新节点密度"""
        if node_id in self.graph.nodes:
            self.graph.nodes[node_id]['current_density'] = density
            # 计算拥堵系数
            congestion = self._calculate_congestion(density)
            self.graph.nodes[node_id]['congestion'] = congestion
    
    def update_edge_congestion(self, from_node, to_node, congestion_factor):
        """更新边的拥堵系数"""
        if self.graph.has_edge(from_node, to_node):
            self.graph[from_node][to_node]['congestion_factor'] = congestion_factor
    
    def _calculate_congestion(self, density):
        """计算拥堵系数"""
        if density < 0.5:
            return 1.0
        elif 0.5 <= density < 1.0:
            return 1.2
        elif 1.0 <= density < 2.0:
            return 1.5
        elif 2.0 <= density < 3.0:
            return 2.0
        else:
            return 3.0
    
    def get_neighbors(self, node_id):
        """获取节点的邻居"""
        return list(self.graph.neighbors(node_id))
    
    def get_nodes_by_type(self, node_type):
        """按类型获取节点"""
        return [node for node, data in self.graph.nodes(data=True) if data['type'] == node_type]
    
    def get_nodes_by_floor(self, floor):
        """按楼层获取节点"""
        return [node for node, data in self.graph.nodes(data=True) if data['floor'] == floor]
    
    def save_graph(self, filename):
        """保存图结构"""
        nx.write_gpickle(self.graph, filename)
    
    def load_graph(self, filename):
        """加载图结构"""
        self.graph = nx.read_gpickle(filename)
    
    def get_graph(self):
        """获取图对象"""
        return self.graph