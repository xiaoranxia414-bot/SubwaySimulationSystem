"""路径规划器 — 支持最短距离、最短时间、最少区域切换、多目标 Pareto 优化"""

import heapq
from collections import deque
from typing import List, Dict, Tuple, Callable, Optional
import networkx as nx


class PathPlanner:
    """路径规划器，提供多种路径规划策略"""

    def __init__(self, station_graph):
        self.station_graph = station_graph
        self.path_cache = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def precompute_all_paths(self):
        """预计算所有入口-出口对的路径（静态路径）"""
        entrance_nodes = self.station_graph.get_nodes_by_type('entrance')
        exit_nodes = self.station_graph.get_nodes_by_type('exit')
        for start in entrance_nodes:
            for end in exit_nodes:
                for mode in ['shortest_time', 'shortest_distance', 'min_switches']:
                    self.find_path(start, end, mode)

    def update_cache_on_congestion(self, threshold=0.5):
        """当拥堵超过阈值时，清空时间相关缓存"""
        keys_to_remove = [k for k in self.path_cache
                          if k[2] in ('shortest_time', 'multi_objective')]
        for k in keys_to_remove:
            del self.path_cache[k]

    def clear_cache(self):
        self.path_cache.clear()

    def find_path(self, start_node, end_node, mode='shortest_time') -> List[str]:
        """查找路径"""
        cache_key = (start_node, end_node, mode)
        if cache_key in self.path_cache:
            self.cache_hits += 1
            return self.path_cache[cache_key]

        self.cache_misses += 1

        if mode == 'shortest_distance':
            path = self._dijkstra(start_node, end_node, weight='distance')
        elif mode == 'shortest_time':
            path = self._dijkstra(start_node, end_node, weight=self._time_weight)
        elif mode == 'min_switches':
            path = self._minimize_area_switches(start_node, end_node)
        elif mode == 'multi_objective':
            path = self._multi_objective_path(start_node, end_node)
        elif mode == 'least_congested':
            path = self._dijkstra(start_node, end_node, weight=self._congestion_weight)
        else:
            path = self._dijkstra(start_node, end_node, weight=self._time_weight)

        if path:
            self.path_cache[cache_key] = path
        return path

    # ── Dijkstra / A* 基础 ──────────────────────────────

    def _dijkstra(self, start, end, weight) -> List[str]:
        """通用 Dijkstra 实现"""
        graph = self.station_graph.get_graph()
        if start not in graph or end not in graph:
            return []

        # 使用 NetworkX 的 shortest_path
        try:
            return nx.shortest_path(graph, start, end, weight=weight)
        except nx.NetworkXNoPath:
            return []

    def _time_weight(self, u, v, d):
        """时间权重 = 基础时间 × 拥堵系数 + 距离/速度 + 跨层代价"""
        base_time = d.get('base_time', 1.0)
        congestion = d.get('congestion_factor', 1.0)
        distance = d.get('distance', 1.0)
        width = d.get('width', 1.0)
        # 通行时间 = max(基础时间, 距离/(宽度修正速度))
        speed = 1.0 * min(2.0, width / 2.0)  # 宽度越宽，速度上限越高
        travel_time = distance / max(speed, 0.1)

        # ── 跨层代价（楼梯/扶梯上下行差异）──
        floor_penalty = 0.0
        u_node = self.station_graph.get_node(u)
        v_node = self.station_graph.get_node(v)
        if u_node and v_node:
            u_floor = u_node.get('floor', 0)
            v_floor = v_node.get('floor', 0)
            floor_diff = abs(v_floor - u_floor)
            if floor_diff > 0:
                u_type = u_node.get('type', '')
                v_type = v_node.get('type', '')
                going_up = v_floor > u_floor
                # 楼梯：上楼慢（8s/层），下楼较快（5s/层）
                if u_type == 'stairs' or v_type == 'stairs':
                    floor_penalty = floor_diff * (8.0 if going_up else 5.0)
                # 扶梯：速度较均匀，上行4s/层，下行3s/层
                elif u_type == 'escalator' or v_type == 'escalator':
                    floor_penalty = floor_diff * (4.0 if going_up else 3.0)
                # 其他跨层（直梯等）：统一 6s/层
                else:
                    floor_penalty = floor_diff * 6.0

        return base_time * congestion + travel_time + floor_penalty

    def _congestion_weight(self, u, v, d):
        """拥堵权重：优先选择拥堵系数小的边"""
        return d.get('congestion_factor', 1.0)

    # ── 最少区域切换 ──────────────────────────────

    def _minimize_area_switches(self, start_node, end_node) -> List[str]:
        """最少区域切换路径 — 使用改进的 Dijkstra，区域切换有惩罚"""
        graph = self.station_graph.get_graph()
        if start_node not in graph or end_node not in graph:
            return []

        # 状态: (累计代价, 切换次数, 当前节点, 当前类型, 路径)
        start_type = self.station_graph.get_node(start_node)['type']
        pq = [(0, 0, start_node, start_type, [start_node])]
        visited = {}  # (node, last_type) -> min_cost

        while pq:
            cost, switches, current, last_type, path = heapq.heappop(pq)
            state = (current, last_type)
            if state in visited and visited[state] <= cost:
                continue
            visited[state] = cost

            if current == end_node:
                return path

            for neighbor in graph.neighbors(current):
                neighbor_type = self.station_graph.get_node(neighbor)['type']
                edge = graph[current][neighbor]
                edge_cost = edge.get('distance', 1.0)
                new_switches = switches + (1 if neighbor_type != last_type else 0)
                # 区域切换有额外惩罚（相当于一次切换 = 走 20m）
                switch_penalty = 20.0 if neighbor_type != last_type else 0.0
                new_cost = cost + edge_cost + switch_penalty

                new_state = (neighbor, neighbor_type)
                if new_state not in visited or visited.get(new_state, float('inf')) > new_cost:
                    heapq.heappush(pq, (new_cost, new_switches, neighbor,
                                        neighbor_type, path + [neighbor]))
        return []

    # ── 多目标优化（Pareto 前沿 + 加权选择）─────────────────────────────

    def _multi_objective_path(self, start_node, end_node) -> List[str]:
        """多目标优化路径

        同时优化：
        1. 时间最短
        2. 距离最短
        3. 区域切换次数最少
        4. 拥挤度最小

        算法：
        - 使用多目标 A* 搜索 Pareto 前沿
        - 对前沿解使用 TOPSIS 方法选择最优折中方案
        """
        graph = self.station_graph.get_graph()
        if start_node not in graph or end_node not in graph:
            return []

        # 获取所有 Pareto 非支配路径（限制数量避免爆炸）
        pareto_paths = self._pareto_search(start_node, end_node, max_paths=8)
        if not pareto_paths:
            return []

        # 使用 TOPSIS 选择最优折中
        best_path = self._topsis_select(pareto_paths)
        return best_path

    def _pareto_search(self, start, end, max_paths=8) -> List[Tuple[List[str], Dict]]:
        """多目标搜索，返回 Pareto 前沿路径集合

        每个状态记录四个目标：time, distance, switches, congestion
        """
        graph = self.station_graph.get_graph()
        # 状态: (time, distance, switches, congestion_sum, node, path)
        # 使用字典按节点存储 Pareto 前沿
        pareto_by_node = {start: [(0, 0, 0, 0, [start])]}
        pq = [(0, 0, 0, 0, start, [start])]

        found_paths = []

        while pq and len(found_paths) < max_paths:
            time_c, dist_c, switch_c, congest_c, current, path = heapq.heappop(pq)

            if current == end:
                found_paths.append((path, {
                    'time': time_c,
                    'distance': dist_c,
                    'switches': switch_c,
                    'congestion': congest_c,
                }))
                continue

            for neighbor in graph.neighbors(current):
                if neighbor in path:  # 避免环路
                    continue

                edge = graph[current][neighbor]
                neighbor_node = self.station_graph.get_node(neighbor)
                current_node = self.station_graph.get_node(current)

                # 计算新增代价
                edge_time = self._time_weight(current, neighbor, edge)
                edge_dist = edge.get('distance', 1.0)
                edge_congest = edge.get('congestion_factor', 1.0)
                switch_add = 1 if neighbor_node['type'] != current_node['type'] else 0

                new_time = time_c + edge_time
                new_dist = dist_c + edge_dist
                new_switch = switch_c + switch_add
                new_congest = congest_c + edge_congest

                new_path = path + [neighbor]
                new_state = (new_time, new_dist, new_switch, new_congest)

                # 检查是否被该节点的现有 Pareto 解支配
                if neighbor not in pareto_by_node:
                    pareto_by_node[neighbor] = []

                dominated = False
                for existing in pareto_by_node[neighbor]:
                    if (existing[0] <= new_time and existing[1] <= new_dist and
                        existing[2] <= new_switch and existing[3] <= new_congest):
                        dominated = True
                        break

                if dominated:
                    continue

                # 移除被新解支配的旧解
                pareto_by_node[neighbor] = [
                    e for e in pareto_by_node[neighbor]
                    if not (new_time <= e[0] and new_dist <= e[1] and
                            new_switch <= e[2] and new_congest <= e[3])
                ]
                pareto_by_node[neighbor].append(new_state)

                heapq.heappush(pq, (new_time, new_dist, new_switch,
                                    new_congest, neighbor, new_path))

        return found_paths

    def _topsis_select(self, pareto_paths: List[Tuple[List[str], Dict]]) -> List[str]:
        """使用 TOPSIS 方法从 Pareto 前沿中选择最优折中方案"""
        if len(pareto_paths) == 1:
            return pareto_paths[0][0]

        # 构建决策矩阵
        objectives = ['time', 'distance', 'switches', 'congestion']
        weights = [0.40, 0.25, 0.20, 0.15]  # 用户偏好权重

        matrix = []
        for path, costs in pareto_paths:
            row = [costs[obj] for obj in objectives]
            matrix.append(row)

        # 归一化
        import numpy as np
        matrix = np.array(matrix, dtype=float)
        col_sums = np.sqrt((matrix ** 2).sum(axis=0))
        col_sums[col_sums == 0] = 1
        norm_matrix = matrix / col_sums

        # 加权
        weighted = norm_matrix * weights

        # 理想解和负理想解（都是越小越好）
        ideal = weighted.min(axis=0)
        nadir = weighted.max(axis=0)

        # 计算距离
        d_ideal = np.sqrt(((weighted - ideal) ** 2).sum(axis=1))
        d_nadir = np.sqrt(((weighted - nadir) ** 2).sum(axis=1))

        # 相对贴近度
        scores = d_nadir / (d_ideal + d_nadir + 1e-9)
        best_idx = int(np.argmax(scores))

        return pareto_paths[best_idx][0]

    # ── 路径评估工具 ──────────────────────────────

    def evaluate_path(self, path: List[str]) -> Dict[str, float]:
        """评估路径的多维度指标"""
        if not path or len(path) < 2:
            return {'time': 0, 'distance': 0, 'switches': 0, 'congestion': 0}

        graph = self.station_graph.get_graph()
        total_time = 0
        total_dist = 0
        total_congest = 0
        switches = 0

        node_types = []
        for node in path:
            info = self.station_graph.get_node(node)
            node_types.append(info['type'] if info else '')

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            if graph.has_edge(u, v):
                edge = graph[u][v]
                total_time += self._time_weight(u, v, edge)
                total_dist += edge.get('distance', 1.0)
                total_congest += edge.get('congestion_factor', 1.0)

        for i in range(len(node_types) - 1):
            if node_types[i] != node_types[i + 1]:
                switches += 1

        return {
            'time': round(total_time, 2),
            'distance': round(total_dist, 2),
            'switches': switches,
            'congestion': round(total_congest / max(len(path) - 1, 1), 2),
            'nodes': len(path),
        }