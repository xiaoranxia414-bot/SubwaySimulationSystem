from utils.priority_queue import PriorityQueue
import networkx as nx

class PathPlanner:
    """路径规划器"""
    
    def __init__(self, station_graph):
        """初始化路径规划器
        
        Args:
            station_graph: 地铁站图
        """
        self.station_graph = station_graph
        # 路径缓存
        self.path_cache = {}
    
    def precompute_all_paths(self):
        """预计算所有入口-出口对的路径"""
        entrance_nodes = self.station_graph.get_nodes_by_type('entrance')
        exit_nodes = self.station_graph.get_nodes_by_type('exit')
        for start in entrance_nodes:
            for end in exit_nodes:
                for mode in ['shortest_time', 'shortest_distance', 'min_switches']:
                    self.find_path(start, end, mode)
    
    def update_cache_on_congestion(self, threshold=0.5):
        """当拥堵超过阈值时更新缓存
        
        Args:
            threshold: 拥堵阈值
        """
        # 简单实现：清空缓存
        self.path_cache.clear()
    
    def find_path(self, start_node, end_node, mode='shortest_time'):
        """查找路径
        
        Args:
            start_node: 起点节点
            end_node: 终点节点
            mode: 路径模式 ('shortest_distance', 'shortest_time', 'multi_objective', 'min_switches')
        
        Returns:
            list: 路径节点列表
        """
        # 检查缓存
        cache_key = (start_node, end_node, mode)
        if cache_key in self.path_cache:
            return self.path_cache[cache_key]
        
        if mode == 'shortest_distance':
            path = self._shortest_distance_path(start_node, end_node)
        elif mode == 'shortest_time':
            path = self._shortest_time_path(start_node, end_node)
        elif mode == 'multi_objective':
            path = self._multi_objective_path(start_node, end_node)
        elif mode == 'min_switches':
            path = self._minimize_area_switches(start_node, end_node)
        else:
            path = self._shortest_time_path(start_node, end_node)
        
        # 缓存结果
        self.path_cache[cache_key] = path
        return path
    
    def _shortest_distance_path(self, start_node, end_node):
        """最短距离路径
        
        Args:
            start_node: 起点节点
            end_node: 终点节点
        
        Returns:
            list: 路径节点列表
        """
        graph = self.station_graph.get_graph()
        
        # 使用Dijkstra算法
        try:
            path = nx.shortest_path(graph, start_node, end_node, weight='distance')
            return path
        except nx.NetworkXNoPath:
            return []
    
    def _shortest_time_path(self, start_node, end_node):
        """最短时间路径
        
        Args:
            start_node: 起点节点
            end_node: 终点节点
        
        Returns:
            list: 路径节点列表
        """
        graph = self.station_graph.get_graph()
        
        # 计算时间权重
        def time_weight(u, v, d):
            distance = d['distance']
            base_time = d.get('base_time', 1.0)
            congestion_factor = d['congestion_factor']
            return base_time * congestion_factor
        
        # 使用Dijkstra算法
        try:
            path = nx.shortest_path(graph, start_node, end_node, weight=time_weight)
            return path
        except nx.NetworkXNoPath:
            return []
    
    def _multi_objective_path(self, start_node, end_node):
        """多目标优化路径
        
        Args:
            start_node: 起点节点
            end_node: 终点节点
        
        Returns:
            list: 路径节点列表
        """
        # 计算多个路径并选择最优
        paths = []
        
        # 最短时间路径
        time_path = self._shortest_time_path(start_node, end_node)
        if time_path:
            paths.append(('time', time_path, self._calculate_path_cost(time_path, 'time')))
        
        # 最短距离路径
        distance_path = self._shortest_distance_path(start_node, end_node)
        if distance_path:
            paths.append(('distance', distance_path, self._calculate_path_cost(distance_path, 'distance')))
        
        # 最少区域切换路径
        min_switch_path = self._minimize_area_switches(start_node, end_node)
        if min_switch_path:
            paths.append(('switches', min_switch_path, self._calculate_path_cost(min_switch_path, 'switches')))
        
        if not paths:
            return []
        
        # 方案A：加权和方法
        best_path = None
        best_score = float('inf')
        
        for path_type, path, cost in paths:
            # 计算综合得分
            score = 0
            if path_type == 'time':
                score = cost * 0.4  # 时间权重
            elif path_type == 'distance':
                score = cost * 0.3  # 距离权重
            elif path_type == 'switches':
                score = cost * 0.3  # 切换次数权重
            
            if score < best_score:
                best_score = score
                best_path = path
        
        return best_path
    
    def _calculate_path_cost(self, path, cost_type):
        """计算路径成本
        
        Args:
            path: 路径节点列表
            cost_type: 成本类型 ('time', 'distance', 'switches')
        
        Returns:
            float: 路径成本
        """
        if not path or len(path) < 2:
            return 0
        
        graph = self.station_graph.get_graph()
        cost = 0
        
        if cost_type == 'time':
            for i in range(len(path) - 1):
                u, v = path[i], path[i+1]
                edge = graph[u][v]
                base_time = edge.get('base_time', 1.0)
                congestion_factor = edge['congestion_factor']
                cost += base_time * congestion_factor
        
        elif cost_type == 'distance':
            for i in range(len(path) - 1):
                u, v = path[i], path[i+1]
                edge = graph[u][v]
                cost += edge['distance']
        
        elif cost_type == 'switches':
            # 计算区域切换次数
            node_types = []
            for node in path:
                node_info = self.station_graph.get_node(node)
                if node_info:
                    node_types.append(node_info['type'])
            
            for i in range(len(node_types) - 1):
                if node_types[i] != node_types[i+1]:
                    cost += 1
        
        return cost
    
    def _minimize_area_switches(self, start_node, end_node):
        """最少区域切换路径
        
        Args:
            start_node: 起点节点
            end_node: 终点节点
        
        Returns:
            list: 路径节点列表
        """
        graph = self.station_graph.get_graph()
        
        # 使用BFS寻找最少区域切换路径
        from collections import deque
        
        visited = set()
        queue = deque()
        queue.append((start_node, [start_node]))
        
        while queue:
            current, path = queue.popleft()
            
            if current == end_node:
                return path
            
            if current in visited:
                continue
            
            visited.add(current)
            
            # 获取当前节点类型
            current_type = self.station_graph.get_node(current)['type']
            
            # 优先选择相同类型的节点
            same_type_neighbors = []
            other_neighbors = []
            
            for neighbor in graph.neighbors(current):
                neighbor_type = self.station_graph.get_node(neighbor)['type']
                if neighbor_type == current_type:
                    same_type_neighbors.append(neighbor)
                else:
                    other_neighbors.append(neighbor)
            
            # 先探索相同类型的邻居
            for neighbor in same_type_neighbors:
                if neighbor not in visited:
                    queue.append((neighbor, path + [neighbor]))
            
            # 再探索不同类型的邻居
            for neighbor in other_neighbors:
                if neighbor not in visited:
                    queue.append((neighbor, path + [neighbor]))
        
        return []
    
    def clear_cache(self):
        """清空路径缓存"""
        self.path_cache.clear()