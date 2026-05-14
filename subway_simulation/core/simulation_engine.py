import random
import numpy as np
from collections import deque, defaultdict
from typing import List, Dict, Tuple, Optional

from utils.spatial_hash import SpatialHash
from utils.stats_collector import StatsCollector
from .passenger import PassengerGenerator


class Train:
    """列车对象"""

    def __init__(self, line_id: str, capacity: int, interval: int,
                 dwell_time_range: Tuple[int, int] = (20, 40),
                 ride_time_range: Tuple[int, int] = (60, 180)):
        self.line_id = line_id
        self.capacity = capacity
        self.interval = interval          # 发车间隔 (秒)
        self.dwell_time_range = dwell_time_range
        self.ride_time_range = ride_time_range

        self.next_arrival = interval      # 下次到达时间
        self.current_dwell = 0            # 当前停站剩余时间
        self.is_at_station = False
        self.boarded_passengers = 0       # 已上车人数

    def update(self, time_step: int):
        """更新列车状态"""
        if self.is_at_station:
            self.current_dwell -= 1
            if self.current_dwell <= 0:
                self.is_at_station = False
                self.next_arrival = time_step + self.interval
                self.boarded_passengers = 0
        else:
            if time_step >= self.next_arrival:
                self.is_at_station = True
                self.current_dwell = int(np.random.uniform(
                    self.dwell_time_range[0], self.dwell_time_range[1]))
                self.boarded_passengers = 0


class SimulationEngine:
    """仿真引擎 — 离散时间步推进"""

    SERVICE_NODE_TYPES = ['ticket', 'security', 'gate']

    def __init__(self, station_graph, path_planner,
                 peak_hours=None, period_rules=None, start_hour=6):
        self.station_graph = station_graph
        self.path_planner = path_planner
        self.passenger_generator = PassengerGenerator(station_graph)
        self.spatial_hash = SpatialHash(cell_size=2.0)
        self.stats_collector = StatsCollector()

        self.passengers: List = []
        self.current_time = 0
        self.queues: Dict[str, deque] = {}
        self.service_counters: Dict[str, int] = {}  # 各服务节点的服务进度

        # 列车系统
        self.trains: Dict[str, Train] = {}
        self._init_trains()

        # 统计
        self.finished_wait_times = {}
        self.finished_travel_times = {}
        self.node_passenger_count = {}
        self.edge_passenger_count = {}

        # 预计算路径
        self.path_planner.precompute_all_paths()

        # 服务率（人/秒）
        self.service_rates = {
            'ticket':   0.4,   # ~2.5秒/人
            'security': 0.25,  # ~4秒/人
            'gate':     0.6,   # ~1.7秒/人
        }

        self.peak_hours = peak_hours if peak_hours else [(7, 9), (17, 19)]
        self.period_rules = period_rules
        self.start_hour = start_hour

        # 基础到达率
        self.base_arrival_rate = 2.0

    def _init_trains(self):
        """初始化列车"""
        platforms = self.station_graph.get_nodes_by_type('platform')
        # 按站台分组，每个站台一条线路
        for i, platform in enumerate(platforms):
            line_id = f"line_{i+1}"
            interval = int(np.random.uniform(120, 300))  # 2~5分钟
            capacity = int(np.random.uniform(300, 600))
            self.trains[line_id] = Train(
                line_id, capacity, interval,
                dwell_time_range=(20, 40),
                ride_time_range=(60, 180)
            )

    # ── 公开接口 ──────────────────────────────

    def add_passenger(self, passenger):
        path = self.path_planner.find_path(
            passenger.start_node, passenger.end_node, passenger.path_strategy)
        if path and len(path) > 1:
            passenger.set_path(path)
            passenger.entry_time = self.current_time
            self.passengers.append(passenger)

    def remove_passenger(self, passenger):
        if passenger in self.passengers:
            passenger.exit_time = self.current_time
            self.finished_wait_times[passenger.passenger_id] = passenger.total_wait_time
            if passenger.entry_time:
                self.finished_travel_times[passenger.passenger_id] = \
                    self.current_time - passenger.entry_time
            self.passengers.remove(passenger)

    def step(self) -> bool:
        """执行一个仿真步（1秒）"""
        self._generate_passengers()
        self._update_trains()
        self._process_queues()
        self._process_boarding()

        # 统计节点和边人数
        self._count_passengers()

        # 更新乘客状态和位置
        self._update_passengers()

        # 冲突检测
        self._handle_conflicts()

        # 更新密度和拥堵
        self._update_densities()

        # 收集统计
        self._collect_stats()

        self.current_time += 1
        return len(self.passengers) > 0 or self.current_time < 3600

    # ── 客流生成 ──────────────────────────────

    def _arrival_rate(self) -> float:
        """计算当前时刻的到达率（人/秒）"""
        current_hour = self.start_hour + self.current_time / 3600.0

        # 1. 如果用户定义了时段规则，优先使用
        if self.period_rules:
            for rule in self.period_rules:
                s, e, level = rule['start'], rule['end'], rule['level']
                if s <= current_hour <= e:
                    center = (s + e) / 2.0
                    sigma = max((e - s) / 4.0, 0.25)
                    mult_map = {'peak': 4.0, 'normal': 1.0, 'trough': 0.2}
                    cm = mult_map.get(level, 1.0)
                    gauss = np.exp(-((current_hour - center) / sigma) ** 2)
                    multiplier = 1.0 + (cm - 1.0) * gauss
                    return float(self.base_arrival_rate * multiplier)
            return float(self.base_arrival_rate)

        # 2. 默认双峰曲线（早高峰 08:00，晚高峰 18:00）
        # 基础流量 + 早高峰高斯 + 晚高峰高斯
        morning_peak = 8.0
        evening_peak = 18.0
        morning_sigma = 1.0
        evening_sigma = 0.8

        morning_factor = 3.0 * np.exp(-((current_hour - morning_peak) / morning_sigma) ** 2)
        evening_factor = 2.5 * np.exp(-((current_hour - evening_peak) / evening_sigma) ** 2)

        rate = self.base_arrival_rate + morning_factor + evening_factor
        # 深夜低谷
        if current_hour < 6 or current_hour > 22:
            rate *= 0.3

        return float(max(rate, 0.1))

    def _generate_passengers(self):
        rate = self._arrival_rate()
        new_passengers = self.passenger_generator.generate_passengers(
            self.current_time, rate)
        for p in new_passengers:
            self.add_passenger(p)

    # ── 列车系统 ──────────────────────────────

    def _update_trains(self):
        """更新所有列车状态"""
        for train in self.trains.values():
            train.update(self.current_time)

    def _process_boarding(self):
        """处理乘客上下车"""
        for train in self.trains.values():
            if not train.is_at_station:
                continue

            # 找到对应的站台（简化：每个线路对应一个站台）
            line_idx = int(train.line_id.split('_')[1]) - 1
            platforms = self.station_graph.get_nodes_by_type('platform')
            if line_idx >= len(platforms):
                continue
            platform = platforms[line_idx]

            # 1. 下车：将 riding 状态且在当前站台的乘客转为 exiting
            for p in list(self.passengers):
                if p.current_state == p.STATE_RIDING and p.current_node == platform:
                    # 到达目的站台，转为出站
                    p.current_state = p.STATE_WALKING
                    p.wait_time = 0
                    # 重新规划到出口的路径
                    exits = self.station_graph.get_nodes_by_type('exit')
                    if exits:
                        p.end_node = random.choice(exits)
                        new_path = self.path_planner.find_path(
                            platform, p.end_node, p.path_strategy)
                        if new_path:
                            p.set_path(new_path)

            # 2. 上车：将 waiting 状态的乘客转为 boarding/riding
            waiting = [p for p in self.passengers
                       if p.current_state == p.STATE_WAITING
                       and p.current_node == platform]

            # 按等待时间排序（FIFO）
            waiting.sort(key=lambda p: p.wait_time, reverse=True)

            boarded = 0
            for p in waiting:
                if train.boarded_passengers >= train.capacity:
                    break
                p.current_state = p.STATE_RIDING
                p.wait_time = 0
                train.boarded_passengers += 1
                boarded += 1

    # ── 队列服务（真实 FIFO + 服务时间）─────────────────────────────

    def _process_queues(self):
        """处理服务节点的排队和服务"""
        # 1. 初始化队列
        for node_id, node_data in self.station_graph.get_graph().nodes(data=True):
            if node_data['type'] in self.SERVICE_NODE_TYPES:
                if node_id not in self.queues:
                    self.queues[node_id] = deque()
                    self.service_counters[node_id] = 0

        # 2. 将处于服务状态的乘客加入对应队列（如果尚未在队列中）
        queue_set = {node_id: set(q) for node_id, q in self.queues.items()}

        for p in self.passengers:
            node_id = p.current_node
            node_info = self.station_graph.get_node(node_id)
            if not node_info:
                continue

            node_type = node_info['type']
            if node_type in self.SERVICE_NODE_TYPES:
                if p not in queue_set.get(node_id, set()):
                    self.queues[node_id].append(p)

        # 3. 服务处理
        for node_id, queue in self.queues.items():
            if not queue:
                continue

            node_info = self.station_graph.get_node(node_id)
            if not node_info:
                continue

            node_type = node_info['type']
            service_rate = self.service_rates.get(node_type, 0.3)

            # 每个时间步，服务节点可以处理 service_rate 个人
            # 使用泊松分布模拟实际服务人数
            mu = service_rate
            capacity = max(1, int(np.random.poisson(mu)))

            served = 0
            while queue and served < capacity:
                passenger = queue[0]
                # 检查乘客是否还在该节点且仍处于服务状态
                if (passenger.current_node == node_id and
                    passenger.current_state in (passenger.STATE_TICKET,
                                                passenger.STATE_SECURITY,
                                                passenger.STATE_GATE)):
                    # 服务完成，切换状态
                    queue.popleft()
                    self._advance_service_state(passenger)
                    served += 1
                else:
                    # 乘客已不在该节点，移出队列
                    queue.popleft()

    def _advance_service_state(self, passenger):
        """将乘客从当前服务状态推进到下一阶段

        服务完成后转为 WALKING，让乘客沿边移动到下一个节点。
        到达下一个节点后，_on_arrive_at_node 会根据节点类型设置正确状态。
        """
        passenger.wait_time = 0
        passenger.current_state = passenger.STATE_WALKING

    # ── 乘客更新 ──────────────────────────────

    def _count_passengers(self):
        """统计各节点和边上的乘客数量"""
        self.node_passenger_count.clear()
        self.edge_passenger_count.clear()

        for p in self.passengers:
            self.node_passenger_count[p.current_node] = \
                self.node_passenger_count.get(p.current_node, 0) + 1

            if p.path and p.path_index < len(p.path) - 1:
                u = p.path[p.path_index]
                v = p.path[p.path_index + 1]
                self.edge_passenger_count[(u, v)] = \
                    self.edge_passenger_count.get((u, v), 0) + 1

    def _update_passengers(self):
        """更新所有乘客状态"""
        # 自适应调整空间哈希单元格
        self.spatial_hash.adaptive_cell_size(len(self.passengers))
        self.spatial_hash.clear()

        # 先插入所有乘客到空间哈希
        for p in self.passengers:
            node_info = self.station_graph.get_node(p.current_node)
            if node_info:
                self.spatial_hash.insert(p, node_info['x'], node_info['y'])

        # 更新状态（使用 list() 避免遍历时修改）
        for p in list(self.passengers):
            old_node = p.current_node
            p.update_state(self)

            # 如果状态是 walking 或 exiting，执行移动
            if p.current_state in (p.STATE_WALKING, p.STATE_EXITING):
                p.move(self)

    # ── 冲突检测 ──────────────────────────────

    def _handle_conflicts(self):
        """检测并处理乘客间冲突（简化版）"""
        # 对每个高密度节点，检查是否有过多乘客
        for node_id, count in self.node_passenger_count.items():
            node_info = self.station_graph.get_node(node_id)
            if not node_info:
                continue

            capacity = node_info['capacity']
            if count > capacity * 0.9:
                # 节点过载，让部分乘客减速
                density = count / node_info.get('area', 100.0)
                self.station_graph.update_node_density(node_id, density)

    # ── 密度与拥堵更新 ──────────────────────────────

    def _update_densities(self):
        """更新所有节点和边的密度/拥堵"""
        for node_id, count in self.node_passenger_count.items():
            node_info = self.station_graph.get_node(node_id)
            if node_info:
                area = node_info.get('area', 100.0)
                density = count / area
                self.station_graph.update_node_density(node_id, density)
                self.stats_collector.update_area_density(node_id, density)

        for u, v, edge_data in self.station_graph.get_graph().edges(data=True):
            edge_pass = self.edge_passenger_count.get((u, v), 0)
            capacity = edge_data.get('capacity', 10)
            # 拥堵系数：基于边容量利用率
            utilization = edge_pass / max(capacity, 1)
            cf = 1.0 + 2.0 * min(utilization, 2.0)
            self.station_graph.update_edge_congestion(u, v, cf)

        # 定期清理路径缓存（每60秒）
        if self.current_time % 60 == 0:
            self.path_planner.update_cache_on_congestion()

    # ── 统计收集 ──────────────────────────────

    def _collect_stats(self):
        for p in self.passengers:
            self.stats_collector.record_passenger_state(
                p.passenger_id, self.current_time,
                p.current_node, p.get_state(), p.total_wait_time)

        for node_id, queue in self.queues.items():
            self.stats_collector.update_queue_length(node_id, len(queue))

        # 列车状态
        for train in self.trains.values():
            self.stats_collector.update_train_status(
                train.line_id, train.is_at_station, train.boarded_passengers)

        self.stats_collector.next_step()

    # ── 查询接口 ──────────────────────────────

    def get_stats(self):
        return {
            'passenger_stats': self.stats_collector.get_passenger_stats(),
            'area_density_stats': self.stats_collector.get_area_density_stats(),
            'queue_stats': self.stats_collector.get_queue_stats(),
            'train_stats': self.stats_collector.get_train_stats(),
        }

    def get_passengers(self):
        return self.passengers

    def get_current_time(self):
        return self.current_time

    def get_finished_stats(self):
        """获取已完成乘客的统计"""
        if not self.finished_wait_times:
            return None
        waits = list(self.finished_wait_times.values())
        travels = list(self.finished_travel_times.values())
        return {
            'finished_count': len(waits),
            'avg_wait_time': sum(waits) / len(waits) if waits else 0,
            'max_wait_time': max(waits) if waits else 0,
            'avg_travel_time': sum(travels) / len(travels) if travels else 0,
            'max_travel_time': max(travels) if travels else 0,
        }

    def reset(self):
        self.passengers.clear()
        self.current_time = 0
        self.stats_collector.clear()
        self.spatial_hash.clear()
        self.queues.clear()
        self.service_counters.clear()
        self.node_passenger_count.clear()
        self.edge_passenger_count.clear()
        self.finished_wait_times.clear()
        self.finished_travel_times.clear()
        self._init_trains()
