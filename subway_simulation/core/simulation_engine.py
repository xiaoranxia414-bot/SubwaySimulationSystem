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

        # ── 新增：成团到达 ──
        self._group_events: List[Dict] = []       # 预设的团体到达事件
        self._group_cooldown = 0                    # 成团到达冷却计时

        # ── 新增：动态速率调整 ──
        self._rate_multiplier = 1.0                 # 动态到达率乘数
        self._congestion_history: deque = deque(maxlen=60)  # 近60步平均拥堵

        # ── 新增：紧急疏散模式 ──
        self.evacuation_mode = False
        self._evacuation_start_time = None

        # ── 新增：双向流 / 对向冲突跟踪 ──
        self._edge_directional_count: Dict[tuple, int] = {}  # (u,v) → 该方向人数

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
        # 紧急疏散检查
        if self.evacuation_mode:
            self._handle_evacuation()

        self._generate_passengers()
        self._update_trains()
        self._process_queues()
        self._process_boarding()

        # 统计节点和边人数（含方向性）
        self._count_passengers()

        # 更新乘客状态和位置
        self._update_passengers()

        # 双向流对向冲突检测
        self._handle_counter_flow_conflicts()

        # 冲突检测
        self._handle_conflicts()

        # 更新密度和拥堵
        self._update_densities()

        # 动态调整生成速率
        self._dynamic_rate_adjustment()

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
        # 紧急疏散时停止生成新乘客
        if self.evacuation_mode:
            return

        rate = self._arrival_rate() * self._rate_multiplier

        # ── 成团到达（大型活动散场等）──
        # 检查是否有预设的团体到达事件
        for event in self._group_events:
            if event['time'] == self.current_time:
                group_size = event.get('size', 30)
                entry_node = event.get('entry_node', None)
                self._spawn_group(group_size, entry_node)

        # 随机成团到达：每 300~600 秒有小概率出现一次 10~50 人的团体
        if self._group_cooldown <= 0:
            if random.random() < 0.003:  # 约每 333 秒触发一次
                group_size = random.randint(10, 50)
                self._spawn_group(group_size)
                self._group_cooldown = random.randint(300, 600)
        else:
            self._group_cooldown -= 1

        # 正常泊松到达
        new_passengers = self.passenger_generator.generate_passengers(
            self.current_time, rate)
        for p in new_passengers:
            self.add_passenger(p)

    def _spawn_group(self, size: int, entry_node: str = None):
        """生成一个团体（集中到达同一入口）"""
        entry_nodes = self.station_graph.get_nodes_by_type('entrance')
        if not entry_nodes:
            return
        # 团体集中从同一个入口进入
        chosen_entry = entry_node if entry_node and entry_node in entry_nodes \
            else random.choice(entry_nodes)

        for _ in range(size):
            p = self.passenger_generator.generate_passenger(self.current_time)
            if p:
                p.start_node = chosen_entry
                p.current_node = chosen_entry
                # 团体成员速度较慢（人群效应）
                p.speed *= random.uniform(0.7, 0.9)
                self.add_passenger(p)

    def schedule_group_arrival(self, time_step: int, size: int = 30,
                               entry_node: str = None):
        """预设一个团体到达事件（供 GUI 调用）"""
        self._group_events.append({
            'time': time_step,
            'size': size,
            'entry_node': entry_node,
        })

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
        """统计各节点和边上的乘客数量（含方向性统计）"""
        self.node_passenger_count.clear()
        self.edge_passenger_count.clear()
        self._edge_directional_count.clear()

        for p in self.passengers:
            self.node_passenger_count[p.current_node] = \
                self.node_passenger_count.get(p.current_node, 0) + 1

            if p.path and p.path_index < len(p.path) - 1:
                u = p.path[p.path_index]
                v = p.path[p.path_index + 1]
                self.edge_passenger_count[(u, v)] = \
                    self.edge_passenger_count.get((u, v), 0) + 1
                # 方向性统计
                self._edge_directional_count[(u, v)] = \
                    self._edge_directional_count.get((u, v), 0) + 1

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

    # ── 双向流 / 对向冲突 ──────────────────────────────

    def _handle_counter_flow_conflicts(self):
        """检测双向流冲突并施加速度惩罚

        如果同一条通道 (u,v) 和 (v,u) 同时有人流，
        两个方向的乘客都会因对向冲突而减速。
        """
        processed = set()
        for (u, v), count_uv in self._edge_directional_count.items():
            if (u, v) in processed or (v, u) in processed:
                continue
            count_vu = self._edge_directional_count.get((v, u), 0)
            if count_uv > 0 and count_vu > 0:
                # 存在对向流，计算冲突系数
                total = count_uv + count_vu
                # 冲突系数：双向越均衡冲突越大（最大2.0）
                balance = min(count_uv, count_vu) / max(count_uv, count_vu)
                conflict_factor = 1.0 + balance * 1.0  # 1.0 ~ 2.0

                # 提高边的拥堵系数
                edge_data = self.station_graph.get_edge(u, v)
                if edge_data:
                    old_cf = edge_data.get('congestion_factor', 1.0)
                    new_cf = max(old_cf, conflict_factor)
                    self.station_graph.update_edge_congestion(u, v, new_cf)
                edge_data_rev = self.station_graph.get_edge(v, u)
                if edge_data_rev:
                    old_cf = edge_data_rev.get('congestion_factor', 1.0)
                    new_cf = max(old_cf, conflict_factor)
                    self.station_graph.update_edge_congestion(v, u, new_cf)

            processed.add((u, v))
            processed.add((v, u))

    # ── 动态到达率调整 ──────────────────────────────

    def _dynamic_rate_adjustment(self):
        """根据当前系统拥堵程度动态调整乘客到达率

        如果系统过于拥挤（平均密度超过阈值），降低到达率，
        模拟现实中车站限流、引导措施。
        """
        if not self.node_passenger_count:
            return

        # 计算当前系统平均密度
        total_density = 0
        count = 0
        for node_id, pcount in self.node_passenger_count.items():
            node_info = self.station_graph.get_node(node_id)
            if node_info:
                area = node_info.get('area', 100.0)
                total_density += pcount / area
                count += 1

        avg_density = total_density / max(count, 1)
        self._congestion_history.append(avg_density)

        # 基于滑动平均拥堵调整乘数
        if len(self._congestion_history) >= 10:
            rolling_avg = sum(self._congestion_history) / len(self._congestion_history)
            if rolling_avg > 2.0:
                # 严重拥堵：大幅降低到达率（限流）
                self._rate_multiplier = max(0.3, self._rate_multiplier - 0.02)
            elif rolling_avg > 1.0:
                # 中度拥堵：轻微降低
                self._rate_multiplier = max(0.5, self._rate_multiplier - 0.005)
            elif rolling_avg < 0.3:
                # 空闲：恢复正常
                self._rate_multiplier = min(1.0, self._rate_multiplier + 0.01)
            else:
                # 正常：缓慢恢复
                self._rate_multiplier = min(1.0, self._rate_multiplier + 0.005)

    # ── 紧急疏散模式 ──────────────────────────────

    def activate_evacuation(self):
        """激活紧急疏散模式"""
        self.evacuation_mode = True
        self._evacuation_start_time = self.current_time

        # 1. 清空所有路径缓存
        self.path_planner.clear_cache()

        # 2. 所有乘客重新规划到最近出口
        exits = self.station_graph.get_nodes_by_type('exit')
        if not exits:
            return

        for p in self.passengers:
            # 跳过已在出站过程中的乘客
            if p.current_state == p.STATE_EXITING:
                continue

            # 停止乘车/候车状态，立即疏散
            p.current_state = p.STATE_EXITING
            p.wait_time = 0

            # 选择最近的出口
            best_exit = None
            best_dist = float('inf')
            cur_info = self.station_graph.get_node(p.current_node)
            if not cur_info:
                continue
            cx, cy = cur_info['x'], cur_info['y']
            for ex in exits:
                ex_info = self.station_graph.get_node(ex)
                if ex_info:
                    dist = ((cx - ex_info['x'])**2 + (cy - ex_info['y'])**2) ** 0.5
                    if dist < best_dist:
                        best_dist = dist
                        best_exit = ex

            if best_exit:
                p.end_node = best_exit
                new_path = self.path_planner.find_path(
                    p.current_node, best_exit, 'shortest_time')
                if new_path and len(new_path) > 1:
                    p.set_path(new_path)

        # 3. 提高移动速度（紧急状态人群速度提升）
        for p in self.passengers:
            p.speed *= 1.3

    def deactivate_evacuation(self):
        """解除紧急疏散模式"""
        self.evacuation_mode = False
        self._evacuation_start_time = None

    def _handle_evacuation(self):
        """疏散模式下的每步处理"""
        # 疏散模式下清空服务队列（不再排队）
        for node_id in list(self.queues.keys()):
            queue = self.queues[node_id]
            for p in list(queue):
                if p.current_state in (p.STATE_TICKET, p.STATE_SECURITY, p.STATE_GATE):
                    p.current_state = p.STATE_EXITING
                    p.wait_time = 0
            queue.clear()

        # 疏散模式下候车乘客也立即出站
        for p in list(self.passengers):
            if p.current_state in (p.STATE_WAITING, p.STATE_RIDING,
                                    p.STATE_BOARDING, p.STATE_TICKET,
                                    p.STATE_SECURITY, p.STATE_GATE):
                p.current_state = p.STATE_EXITING
                p.wait_time = 0

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
        self._edge_directional_count.clear()
        self._group_events.clear()
        self._group_cooldown = 0
        self._rate_multiplier = 1.0
        self._congestion_history.clear()
        self.evacuation_mode = False
        self._evacuation_start_time = None
        self._init_trains()
