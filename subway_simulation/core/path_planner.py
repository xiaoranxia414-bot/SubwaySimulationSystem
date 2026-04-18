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
    
    def find_path(self, start_node, end_node, mode='shortest_time', passenger_profile=None):
        """查找路径
        
        Args:
            start_node: 起点节点
            end_node: 终点节点
            mode: 路径模式 ('shortest_distance', 'shortest_time', 'multi_objective', 'min_switches')
            passenger_profile: 乘客个人特征
        
        Returns:
            list: 路径节点列表
        """
        # 检查缓存
        cache_key = (start_node, end_node, mode, tuple(sorted(passenger_profile.items())) if passenger_profile else None)
        if cache_key in self.path_cache:
            return self.path_cache[cache_key]
        
        if mode == 'shortest_distance':
            path = self._shortest_distance_path(start_node, end_node)
        elif mode == 'shortest_time':
            path = self._shortest_time_path(start_node, end_node)
        elif mode == 'multi_objective':
            path = self._multi_objective_path(start_node, end_node, passenger_profile)
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
    
    def _multi_objective_path(self, start_node, end_node, passenger_profile=None):
        """多目标优化路径
        
        Args:
            start_node: 起点节点
            end_node: 终点节点
            passenger_profile: 乘客个人特征
        
        Returns:
            list: 路径节点列表
        """
        # 计算多个路径并选择最优
        paths = []
        
        # 最短时间路径
        time_path = self._shortest_time_path(start_node, end_node)
        if time_path:
            time_cost = self._calculate_path_cost(time_path, 'time')
            paths.append(('time', time_path, time_cost))
        
        # 最短距离路径
        distance_path = self._shortest_distance_path(start_node, end_node)
        if distance_path:
            distance_cost = self._calculate_path_cost(distance_path, 'distance')
            paths.append(('distance', distance_path, distance_cost))
        
        # 最少区域切换路径
        min_switch_path = self._minimize_area_switches(start_node, end_node)
        if min_switch_path:
            switch_cost = self._calculate_path_cost(min_switch_path, 'switches')
            paths.append(('switches', min_switch_path, switch_cost))
        
        # 最少拥挤路径
        least_crowded_path = self._least_crowded_path(start_node, end_node)
        if least_crowded_path:
            crowd_cost = self._calculate_path_cost(least_crowded_path, 'crowdedness')
            paths.append(('crowdedness', least_crowded_path, crowd_cost))
        
        if not paths:
            return []
        
        # 根据乘客特征调整权重
        weights = self._get_adaptive_weights(passenger_profile)
        
        # 计算每个路径的综合得分
        best_path = None
        best_score = float('inf')
        
        for path_type, path, cost in paths:
            # 计算综合得分
            score = 0
            if path_type == 'time':
                score = cost * weights['time']
            elif path_type == 'distance':
                score = cost * weights['distance']
            elif path_type == 'switches':
                score = cost * weights['switches']
            elif path_type == 'crowdedness':
                score = cost * weights['crowdedness']
            
            if score < best_score:
                best_score = score
                best_path = path
        
        return best_path
    
    def _least_crowded_path(self, start_node, end_node):
        """最少拥挤路径
        
        Args:
            start_node: 起点节点
            end_node: 终点节点
        
        Returns:
            list: 路径节点列表
        """
        graph = self.station_graph.get_graph()
        
        # 计算拥挤度权重
        def crowd_weight(u, v, d):
            node_u = self.station_graph.get_node(u)
            node_v = self.station_graph.get_node(v)
            congestion_u = node_u.get('congestion', 1.0) if node_u else 1.0
            congestion_v = node_v.get('congestion', 1.0) if node_v else 1.0
            edge_congestion = d.get('congestion_factor', 1.0)
            return (congestion_u + congestion_v + edge_congestion) / 3
        
        # 使用Dijkstra算法
        try:
            path = nx.shortest_path(graph, start_node, end_node, weight=crowd_weight)
            return path
        except nx.NetworkXNoPath:
            return []
    
    def _get_adaptive_weights(self, passenger_profile):
        """根据乘客特征获取自适应权重
        
        Args:
            passenger_profile: 乘客个人特征
        
        Returns:
            dict: 各目标的权重
        """
        # 默认权重
        weights = {
            'time': 0.3,
            'distance': 0.2,
            'switches': 0.2,
            'crowdedness': 0.3
        }
        
        if passenger_profile:
            # 根据乘客熟悉度调整权重
            familiarity = passenger_profile.get('familiarity', 0.5)
            if familiarity > 0.7:
                # 熟悉的乘客更注重时间
                weights['time'] = 0.4
                weights['crowdedness'] = 0.2
            elif familiarity < 0.3:
                # 不熟悉的乘客更注重距离和路径简单性
                weights['distance'] = 0.3
                weights['switches'] = 0.3
            
            # 根据乘客耐心度调整权重
            patience = passenger_profile.get('patience', 0.5)
            if patience < 0.3:
                # 耐心低的乘客更注重时间和拥挤度
                weights['time'] = 0.4
                weights['crowdedness'] = 0.3
            
            # 根据乘客速度调整权重
            speed = passenger_profile.get('speed', 1.0)
            if speed > 1.1:
                # 速度快的乘客更注重时间
                weights['time'] = 0.4
                weights['distance'] = 0.1
        
        return weights
    
    def _calculate_path_cost(self, path, cost_type):
        """计算路径成本
        
        Args:
            path: 路径节点列表
            cost_type: 成本类型 ('time', 'distance', 'switches', 'crowdedness')
        
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
        
        elif cost_type == 'crowdedness':
            # 计算拥挤度成本
            for i in range(len(path) - 1):
                u, v = path[i], path[i+1]
                # 节点拥挤度
                node_u = self.station_graph.get_node(u)
                node_v = self.station_graph.get_node(v)
                congestion_u = node_u.get('congestion', 1.0) if node_u else 1.0
                congestion_v = node_v.get('congestion', 1.0) if node_v else 1.0
                # 边拥挤度
                edge = graph[u][v]
                edge_congestion = edge.get('congestion_factor', 1.0)
                # 平均拥挤度
                avg_congestion = (congestion_u + congestion_v + edge_congestion) / 3
                cost += avg_congestion
        
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