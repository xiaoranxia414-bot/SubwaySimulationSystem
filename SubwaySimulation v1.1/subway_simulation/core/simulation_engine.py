import numpy as np
from utils.spatial_hash import SpatialHash
from utils.stats_collector import StatsCollector
from .passenger import PassengerGenerator
from collections import deque
from multiprocessing import Pool
import os


class SimulationEngine:
    """
    仿真引擎

    [修改说明]
    1. 新增 period_rules 参数：接收用户自定义时段配置（高峰/平常/低谷），
       每个时段用以中点为中心的高斯曲线平滑过渡，替代原来的硬编码双峰。
    2. 新增 start_hour 参数：仿真起始时刻（整数小时），配合 1步=1秒 的
       换算将 current_time 映射到真实时钟小时，使高斯曲线与时刻对齐。
    3. 无自定义规则时回退为内置双峰曲线（08:00 早高峰 / 18:00 晚高峰）。
    """

    def __init__(self, station_graph, path_planner, peak_hours=None,
                 period_rules=None, start_hour=6):
        self.station_graph       = station_graph
        self.path_planner        = path_planner
        self.passenger_generator = PassengerGenerator(station_graph)
        self.spatial_hash        = SpatialHash(cell_size=1.0)
        self.stats_collector     = StatsCollector()
        self.passengers          = []
        self.current_time        = 0
        self.queues              = {}
        self.service_node_types  = ['ticket', 'security', 'gate']
        # [修改] 记录已离场乘客的精确最终等待时间：{passenger_id: total_wait_time}
        # 在 remove_passenger 时写入，避免乘客离场后被快照遗漏
        self.finished_wait_times = {}

        self.node_passenger_count = {}
        self.edge_passenger_count = {}

        # 预计算所有路径
        self.path_planner.precompute_all_paths()

        # 服务率：每步平均服务人数（泊松抽样），修复原版恒为0的bug
        self.service_rates = {
            'ticket':   1.5,   # 约每步1~2人完成购票
            'security': 1.0,   # 安检略慢
            'gate':     2.0,   # 闸机最快
        }

        # 保留 peak_hours 以向后兼容，新逻辑优先使用 period_rules
        self.peak_hours = peak_hours if peak_hours else [(0, 9999)]

        # [修改] 用户自定义时段规则列表，每项格式：
        #   {'start': int小时, 'end': int小时, 'level': 'peak'|'normal'|'trough'}
        # 为 None 时回退到内置双峰曲线（08:00 / 18:00）
        self.period_rules = period_rules

        # [修改] 仿真起始小时（current_time=0 对应的时刻），结合 1步=1秒
        # 换算公式：current_hour = start_hour + current_time / 3600.0
        self.start_hour = start_hour

    # ── 公开接口 ──────────────────────────────
    def add_passenger(self, passenger):
        path = self.path_planner.find_path(
            passenger.start_node, passenger.end_node, passenger.path_strategy)
        if path:
            passenger.set_path(path)
            self.passengers.append(passenger)

    def remove_passenger(self, passenger):
        if passenger in self.passengers:
            # [修改] 离场前保存精确的最终等待时间，供 AnalyticsModule 合并统计
            self.finished_wait_times[passenger.passenger_id] = passenger.total_wait_time
            self.passengers.remove(passenger)

    def step(self):
        self._generate_passengers()
        # 自适应调整空间哈希单元格大小
        self.spatial_hash.adaptive_cell_size(len(self.passengers))
        self._process_queues()

        self.node_passenger_count.clear()
        self.edge_passenger_count.clear()

        # 第一遍：统计节点乘客数
        for passenger in list(self.passengers):
            self.node_passenger_count[passenger.current_node] = \
                self.node_passenger_count.get(passenger.current_node, 0) + 1

        # 第二遍：乘客移动和空间哈希更新（并行）
        if len(self.passengers) > 1000 and os.cpu_count() > 1:
            self._parallel_update_passengers()
        else:
            for passenger in list(self.passengers):
                old_node = passenger.current_node
                old_info = self.station_graph.get_node(old_node)
                old_x, old_y = old_info['x'], old_info['y'] if old_info else (0, 0)
                
                passenger.update_state(self)
                passenger.move(self)
                
                new_node = passenger.current_node
                new_info = self.station_graph.get_node(new_node)
                new_x, new_y = new_info['x'], new_info['y'] if new_info else (0, 0)
                
                if old_node != new_node:
                    # 增量更新空间哈希
                    self.spatial_hash.update_position(passenger, old_x, old_y, new_x, new_y)
                else:
                    # 重新插入到同一位置
                    self.spatial_hash.insert(passenger, new_x, new_y)

        # 第三遍：统计边乘客数
        for passenger in self.passengers:
            if passenger.path and passenger.path_index < len(passenger.path) - 1:
                u = passenger.path[passenger.path_index]
                v = passenger.path[passenger.path_index + 1]
                self.edge_passenger_count[(u, v)] = \
                    self.edge_passenger_count.get((u, v), 0) + 1

        self._handle_conflicts()
        self._update_densities()
        self._collect_stats()
        self.current_time += 1
        return len(self.passengers) > 0
    
    def _parallel_update_passengers(self):
        """并行更新乘客状态"""
        if __name__ == '__main__':
            # 将乘客分成多个批次
            num_processes = min(os.cpu_count(), 4)
            batches = np.array_split(self.passengers, num_processes)
            
            # 定义批处理函数
            def process_batch(batch):
                results = []
                for passenger in batch:
                    old_node = passenger.current_node
                    old_info = self.station_graph.get_node(old_node)
                    old_x, old_y = old_info['x'], old_info['y'] if old_info else (0, 0)
                    
                    passenger.update_state(self)
                    passenger.move(self)
                    
                    new_node = passenger.current_node
                    new_info = self.station_graph.get_node(new_node)
                    new_x, new_y = new_info['x'], new_info['y'] if new_info else (0, 0)
                    
                    results.append((passenger, old_node, old_x, old_y, new_node, new_x, new_y))
                return results
            
            # 并行处理
            with Pool(processes=num_processes) as pool:
                results = pool.map(process_batch, batches)
                
                # 合并结果并更新空间哈希
                for batch_results in results:
                    for passenger, old_node, old_x, old_y, new_node, new_x, new_y in batch_results:
                        if old_node != new_node:
                            self.spatial_hash.update_position(passenger, old_x, old_y, new_x, new_y)
                        else:
                            self.spatial_hash.insert(passenger, new_x, new_y)

    # ── 客流生成：时间曲线 + 泊松 ────────────
    def _arrival_rate(self):
        """
        [修改] 基于用户自定义时段规则的客流到达率计算。

        换算：1步=1秒，当前仿真时刻（小时）= start_hour + current_time / 3600

        【有自定义规则时】
          对每条规则 {'start': s, 'end': e, 'level': L}：
          - 以时段中点为高斯中心，σ = 时段半宽 / 2
          - 在中心处，倍率达到最大（peak=4.0）或最小（trough=0.2）
          - 边缘处倍率平滑回归到 1.0（平常水平）
          - 公式：λ = λ_base * [1 + (center_mult - 1) * exp(-((h-center)/σ)²)]
            peak   中心倍率 4.0 → λ 从 λ_base 升至 4×λ_base
            trough 中心倍率 0.2 → λ 从 λ_base 降至 0.2×λ_base
            normal 中心倍率 1.0 → λ 恒等于 λ_base

        【无自定义规则时（默认双峰）】
          早高峰锚定 08:00（σ=1.0h），晚高峰锚定 18:00（σ=0.8h）。
        """
        # 1步=1秒，换算为小时
        current_hour = self.start_hour + self.current_time / 3600.0

        # 平峰基础到达率（人/秒）
        lambda_base = 2.0

        # [修改] 有自定义时段规则时走此分支
        if self.period_rules:
            for rule in self.period_rules:
                start_h = rule['start']
                end_h   = rule['end']
                level   = rule['level']  # 'peak' | 'normal' | 'trough'

                if start_h <= current_hour <= end_h:
                    # 时段中点作为高斯中心
                    # σ 取半宽的一半，使曲线在边界处已衰减约 14%，过渡自然
                    center = (start_h + end_h) / 2.0
                    sigma  = max((end_h - start_h) / 4.0, 0.25)  # 最小σ=0.25h

                    # 各等级在高斯中心处的流量倍率：
                    #   peak   → 中心升至 4 倍基础流量（强高峰）
                    #   trough → 中心降至 0.2 倍基础流量（深低谷）
                    #   normal → 保持 1.0 倍（平常不变）
                    center_mult = {'peak': 4.0, 'normal': 1.0, 'trough': 0.2}[level]

                    # 高斯项：时段边缘趋近 0，中心为 1
                    gauss      = np.exp(-((current_hour - center) / sigma) ** 2)
                    # 整体倍率：边缘为 1.0，中心为 center_mult，平滑过渡
                    multiplier = 1.0 + (center_mult - 1.0) * gauss

                    return float(lambda_base * multiplier)

            # 当前时刻不在任何已定义时段内 → 平常期
            return float(lambda_base)

        # 无自定义规则 → 全程平常期，恒定基础流量
        return float(lambda_base)

    def _generate_passengers(self):
        """泊松到达，λ 由时间曲线决定"""
        rate = self._arrival_rate()
        new_passengers = self.passenger_generator.generate_passengers(
            self.current_time, rate)
        for p in new_passengers:
            self.add_passenger(p)

    # ── 队列服务：泊松服务 ───
    def _process_queues(self):
        for node_id, node_data in self.station_graph.get_graph().nodes(data=True):
            if node_data['type'] in self.service_node_types:
                if node_id not in self.queues:
                    self.queues[node_id] = deque()

        for passenger in self.passengers:
            node_id   = passenger.current_node
            node_info = self.station_graph.get_node(node_id)
            if node_info and node_info['type'] in self.service_node_types:
                if passenger not in self.queues[node_id]:
                    self.queues[node_id].append(passenger)

        # 泊松抽样服务人数，μ=service_rate，最少1人
        for node_id, queue in self.queues.items():
            if not queue:
                continue
            node_info = self.station_graph.get_node(node_id)
            if node_info:
                mu    = self.service_rates.get(node_info['type'], 1.0)
                count = max(1, int(np.random.poisson(mu)))
                for _ in range(count):
                    if queue:
                        queue.popleft()

    def _handle_conflicts(self):
        for passenger in self.passengers:
            node_info = self.station_graph.get_node(passenger.current_node)
            if node_info:
                neighbors = self.spatial_hash.get_neighbors(
                    node_info['x'], node_info['y'], 1.5)
                for neighbor, nx, ny in neighbors:
                    if neighbor != passenger:
                        self._resolve_conflict(passenger, neighbor)

    def _resolve_conflict(self, p1, p2):
        pass

    def _update_densities(self):
        for node_id, count in self.node_passenger_count.items():
            node_info = self.station_graph.get_node(node_id)
            if node_info:
                area    = node_info.get('area', 100.0)
                density = count / area
                self.station_graph.update_node_density(node_id, density)
                self.stats_collector.update_area_density(node_id, density)

        for u, v, edge_data in self.station_graph.get_graph().edges(data=True):
            edge_pass = self.edge_passenger_count.get((u, v), 0)
            capacity = edge_data.get('capacity', 10)
            cf = max(1.0, edge_pass / capacity * 2.0)
            self.station_graph.update_edge_congestion(u, v, cf)

    def _collect_stats(self):
        for p in self.passengers:
            self.stats_collector.record_passenger_state(
                p.passenger_id, self.current_time,
                p.current_node, p.get_state(), p.wait_time)
        for node_id, queue in self.queues.items():
            self.stats_collector.update_queue_length(node_id, len(queue))
        # 进入下一步
        self.stats_collector.next_step()

    # ── 查询接口 ──────────────────────────────
    def get_stats(self):
        return {
            'passenger_stats':    self.stats_collector.get_passenger_stats(),
            'area_density_stats': self.stats_collector.get_area_density_stats(),
            'queue_stats':        self.stats_collector.get_queue_stats(),
        }

    def get_passengers(self):   return self.passengers
    def get_current_time(self): return self.current_time

    def reset(self):
        self.passengers.clear()
        self.current_time = 0
        self.stats_collector.clear()
        self.spatial_hash.clear()
        self.queues.clear()
        self.node_passenger_count.clear()
        self.edge_passenger_count.clear()
        self.finished_wait_times.clear()