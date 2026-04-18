from utils.spatial_hash import SpatialHash
from utils.stats_collector import StatsCollector
from .passenger import PassengerGenerator
from collections import deque

class SimulationEngine:
    """仿真引擎"""
    
    def __init__(self, station_graph, path_planner, peak_hours=None):
        """初始化仿真引擎
        
        Args:
            station_graph: 地铁站图
            path_planner: 路径规划器
            peak_hours: 高峰期时间段列表 [(start1, end1), (start2, end2), ...]
        """
        self.station_graph = station_graph
        self.path_planner = path_planner
        self.passenger_generator = PassengerGenerator(station_graph)
        self.spatial_hash = SpatialHash(cell_size=1.0)
        self.stats_collector = StatsCollector()
        self.passengers = []
        self.current_time = 0
        # 队列管理
        self.queues = {}
        # 服务节点类型
        self.service_node_types = ['ticket', 'security', 'gate']
        # 服务率（人/秒）
        self.service_rates = {
            'ticket': 0.3,  # 约3秒/人
            'security': 0.2,  # 约5秒/人
            'gate': 0.5  # 约2秒/人
        }
        # 高峰期时间段
        self.peak_hours = peak_hours if peak_hours else [(7, 9), (17, 19)]
    
    def add_passenger(self, passenger):
        """添加乘客
        
        Args:
            passenger: 乘客对象
        """
        # 为乘客规划路径
        # 准备乘客特征
        passenger_profile = {
            'speed': passenger.speed,
            'patience': passenger.patience,
            'familiarity': passenger.familiarity
        }
        path = self.path_planner.find_path(passenger.start_node, passenger.end_node, 
                                         passenger.path_strategy, passenger_profile)
        if path:
            passenger.set_path(path)
            self.passengers.append(passenger)
    
    def remove_passenger(self, passenger):
        """移除乘客
        
        Args:
            passenger: 乘客对象
        """
        if passenger in self.passengers:
            self.passengers.remove(passenger)
    
    def step(self):
        """执行一个时间步
        
        Returns:
            bool: 仿真是否继续
        """
        # 生成新乘客
        self._generate_passengers()
        
        # 清空空间哈希
        self.spatial_hash.clear()
        
        # 处理队列服务
        self._process_queues()
        
        # 检查拥堵情况，可能需要重新规划路径
        if self.current_time % 5 == 0:  # 每5步检查一次
            self._reevaluate_paths()
        
        # 更新乘客状态和位置
        for passenger in self.passengers:
            # 更新状态
            passenger.update_state(self)
            
            # 移动乘客
            passenger.move(self)
            
            # 获取乘客位置
            node_info = self.station_graph.get_node(passenger.current_node)
            if node_info:
                x, y = node_info['x'], node_info['y']
                # 添加到空间哈希
                self.spatial_hash.insert(passenger, x, y)
        
        # 检测和处理冲突
        self._handle_conflicts()
        
        # 更新密度
        self._update_densities()
        
        # 收集统计数据
        self._collect_stats()
        
        # 增加时间
        self.current_time += 1
        
        # 检查是否还有乘客
        return len(self.passengers) > 0
    
    def _reevaluate_paths(self):
        """重新评估路径
        
        当拥堵超过阈值时，为受影响的乘客重新规划路径
        """
        # 检查节点拥堵情况
        congested_nodes = []
        for node_id, node_data in self.station_graph.get_graph().nodes(data=True):
            if node_data.get('congestion', 1.0) > 2.0:  # 拥堵阈值
                congested_nodes.append(node_id)
        
        # 检查边拥堵情况
        congested_edges = []
        for u, v, edge_data in self.station_graph.get_graph().edges(data=True):
            if edge_data.get('congestion_factor', 1.0) > 2.0:  # 拥堵阈值
                congested_edges.append((u, v))
        
        # 如果有拥堵，重新规划路径
        if congested_nodes or congested_edges:
            for passenger in self.passengers:
                # 检查乘客当前路径是否经过拥堵区域
                if self._path_contains_congestion(passenger.path, congested_nodes, congested_edges):
                    # 重新规划路径
                    passenger_profile = {
                        'speed': passenger.speed,
                        'patience': passenger.patience,
                        'familiarity': passenger.familiarity
                    }
                    new_path = self.path_planner.find_path(
                        passenger.current_node, 
                        passenger.end_node, 
                        mode='multi_objective',
                        passenger_profile=passenger_profile
                    )
                    if new_path and new_path != passenger.path:
                        passenger.set_path(new_path)
    
    def _path_contains_congestion(self, path, congested_nodes, congested_edges):
        """检查路径是否包含拥堵区域
        
        Args:
            path: 路径节点列表
            congested_nodes: 拥堵节点列表
            congested_edges: 拥堵边列表
        
        Returns:
            bool: 是否包含拥堵区域
        """
        if not path:
            return False
        
        # 检查节点拥堵
        for node in path:
            if node in congested_nodes:
                return True
        
        # 检查边拥堵
        for i in range(len(path) - 1):
            edge = (path[i], path[i+1])
            if edge in congested_edges:
                return True
        
        return False
    
    def _generate_passengers(self):
        """生成新乘客"""
        # 检查是否为高峰期
        is_peak_hour = False
        for start, end in self.peak_hours:
            if start <= self.current_time <= end:
                is_peak_hour = True
                break
        
        # 高峰期生成更多乘客
        if is_peak_hour:
            rate = 10  # 高峰期生成速率
        else:
            rate = 5  # 平峰期生成速率
        
        new_passengers = self.passenger_generator.generate_passengers(self.current_time, rate)
        for passenger in new_passengers:
            self.add_passenger(passenger)
    
    def _process_queues(self):
        """处理队列服务"""
        # 为服务节点创建队列
        for node_id, node_data in self.station_graph.get_graph().nodes(data=True):
            if node_data['type'] in self.service_node_types:
                if node_id not in self.queues:
                    self.queues[node_id] = deque()
        
        # 将乘客加入对应节点的队列
        for passenger in self.passengers:
            node_id = passenger.current_node
            node_info = self.station_graph.get_node(node_id)
            if node_info and node_info['type'] in self.service_node_types:
                if passenger not in self.queues[node_id]:
                    self.queues[node_id].append(passenger)
        
        # 处理每个队列的服务
        for node_id, queue in self.queues.items():
            node_info = self.station_graph.get_node(node_id)
            if node_info:
                service_rate = self.service_rates.get(node_info['type'], 0.1)
                # 计算本时间步可服务的人数
                service_count = int(service_rate * 1.0)  # dt=1.0
                
                # 服务乘客
                for _ in range(service_count):
                    if queue:
                        passenger = queue.popleft()
                        # 乘客状态会在update_state中更新
    
    def _handle_conflicts(self):
        """处理冲突"""
        # 检查每个乘客的邻居
        for passenger in self.passengers:
            node_info = self.station_graph.get_node(passenger.current_node)
            if node_info:
                x, y = node_info['x'], node_info['y']
                # 获取附近的乘客
                neighbors = self.spatial_hash.get_neighbors(x, y, 1.5)
                
                # 处理冲突
                for neighbor, nx, ny in neighbors:
                    if neighbor != passenger:
                        # 简单的冲突处理：调整位置
                        self._resolve_conflict(passenger, neighbor)
    
    def _resolve_conflict(self, passenger1, passenger2):
        """解决冲突
        
        Args:
            passenger1: 乘客1
            passenger2: 乘客2
        """
        # 简单的冲突处理：让耐心度低的乘客等待
        if passenger1.patience < passenger2.patience:
            # 乘客1等待
            pass
        else:
            # 乘客2等待
            pass
    
    def _update_densities(self):
        """更新密度"""
        # 统计每个节点的乘客数量
        node_counts = {}
        for passenger in self.passengers:
            node_id = passenger.current_node
            if node_id not in node_counts:
                node_counts[node_id] = 0
            node_counts[node_id] += 1
        
        # 计算密度并更新
        for node_id, count in node_counts.items():
            node_info = self.station_graph.get_node(node_id)
            if node_info:
                area = node_info.get('area', 100.0)
                density = count / area
                self.station_graph.update_node_density(node_id, density)
                self.stats_collector.update_area_density(node_id, density)
        
        # 更新边的拥堵系数
        for u, v, edge_data in self.station_graph.get_graph().edges(data=True):
            # 计算边上的乘客数量
            edge_passengers = sum(1 for p in self.passengers 
                                if p.path and p.path_index < len(p.path) - 1 
                                and p.path[p.path_index] == u 
                                and p.path[p.path_index + 1] == v)
            capacity = edge_data.get('capacity', 10)
            congestion_factor = max(1.0, edge_passengers / capacity * 2.0)
            self.station_graph.update_edge_congestion(u, v, congestion_factor)
    
    def _collect_stats(self):
        """收集统计数据"""
        for passenger in self.passengers:
            self.stats_collector.record_passenger_state(
                passenger.passenger_id,
                self.current_time,
                passenger.current_node,
                passenger.get_state(),
                passenger.wait_time
            )
        
        # 收集队列统计数据
        for node_id, queue in self.queues.items():
            queue_length = len(queue)
            self.stats_collector.update_queue_length(node_id, queue_length)
    
    def get_stats(self):
        """获取统计数据"""
        return {
            'passenger_stats': self.stats_collector.get_passenger_stats(),
            'area_density_stats': self.stats_collector.get_area_density_stats(),
            'queue_stats': self.stats_collector.get_queue_stats()
        }
    
    def get_passengers(self):
        """获取所有乘客"""
        return self.passengers
    
    def get_current_time(self):
        """获取当前时间"""
        return self.current_time
    
    def reset(self):
        """重置仿真"""
        self.passengers.clear()
        self.current_time = 0
        self.stats_collector.clear()
        self.spatial_hash.clear()
        self.queues.clear()