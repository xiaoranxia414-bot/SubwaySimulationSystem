import random
import math
import numpy as np
from typing import List, Optional, Dict


class Passenger:
    """乘客对象 — 基于有限状态机的完整行为模拟"""

    STATE_ENTERING  = 'entering'    # 刚进入车站
    STATE_TICKET    = 'ticket'      # 购票/刷卡
    STATE_SECURITY  = 'security'    # 安检
    STATE_GATE      = 'gate'        # 过闸机
    STATE_WALKING   = 'walking'     # 在通道中行走
    STATE_WAITING   = 'waiting'     # 站台候车
    STATE_BOARDING  = 'boarding'    # 上车
    STATE_RIDING    = 'riding'      # 乘车中
    STATE_EXITING   = 'exiting'     # 出站

    ALL_STATES = [STATE_ENTERING, STATE_TICKET, STATE_SECURITY, STATE_GATE,
                  STATE_WALKING, STATE_WAITING, STATE_BOARDING, STATE_RIDING, STATE_EXITING]

    def __init__(self, passenger_id, start_node, end_node,
                 speed=1.0, patience=0.5, familiarity=0.5,
                 path_strategy='shortest_time',
                 has_ticket=False):
        self.passenger_id = passenger_id
        self.start_node = start_node
        self.end_node = end_node
        self.speed = speed
        self.patience = patience          # 0~1，越高越愿意等待/排队
        self.familiarity = familiarity    # 0~1，越高操作越快
        self.path_strategy = path_strategy
        self.has_ticket = has_ticket      # 是否有票（手机支付/交通卡）

        self.current_node = start_node
        self.current_state = self.STATE_ENTERING
        self.path: List[str] = []
        self.path_index = 0
        self.move_progress = 0.0
        self.blocked_time = 0

        # 时间统计
        self.wait_time = 0              # 当前状态已等待时间（步）
        self.total_wait_time = 0        # 累计排队/等待时间
        self.total_travel_time = 0      # 累计行走时间
        self.entry_time = None          # 进入系统的时间
        self.exit_time = None           # 离开系统的时间

        # 各阶段期望服务时长（基于属性和随机性）
        # 熟悉度高 → 购票/过闸更快
        self._ticket_duration = self._sample_service_time(3.0, familiarity)
        self._security_duration = self._sample_service_time(5.0, 0.3)  # 安检较固定
        self._gate_duration = self._sample_service_time(2.0, familiarity * 0.5)

        # 重规划冷却
        self._last_replan = -999
        self._replan_cooldown = max(10, int(30 * (1 - patience)))

    @staticmethod
    def _sample_service_time(base, familiarity, min_time=1):
        """基于泊松分布采样服务时间"""
        lam = base / (0.5 + familiarity)
        return max(min_time, int(np.random.poisson(lam)))

    def set_path(self, path: List[str]):
        self.path = path
        self.path_index = 0
        self.move_progress = 0.0

    # ── 状态机主入口 ──────────────────────────────

    def update_state(self, simulation):
        """每个时间步调用，更新乘客状态"""
        self.total_travel_time += 1

        handlers = {
            self.STATE_ENTERING:  self._handle_entering,
            self.STATE_TICKET:    self._handle_ticket,
            self.STATE_SECURITY:  self._handle_security,
            self.STATE_GATE:      self._handle_gate,
            self.STATE_WALKING:   self._handle_walking,
            self.STATE_WAITING:   self._handle_waiting,
            self.STATE_BOARDING:  self._handle_boarding,
            self.STATE_RIDING:    self._handle_riding,
            self.STATE_EXITING:   self._handle_exiting,
        }
        handler = handlers.get(self.current_state)
        if handler:
            handler(simulation)

    # ── 各状态处理器 ──────────────────────────────

    def _handle_entering(self, simulation):
        """进站后，开始沿路径走向第一个服务节点"""
        # 统一转为 walking，让 move 带乘客走向下一个节点
        # 到达 ticket/security 节点后，_on_arrive_at_node 会根据情况设置正确状态
        self.current_state = self.STATE_WALKING

    def _handle_ticket(self, simulation):
        """购票/刷卡 — 需要排队服务"""
        self.wait_time += 1
        # 是否被服务完成由 simulation_engine 的队列处理决定
        # 这里只记录等待
        self.total_wait_time += 1

    def _handle_security(self, simulation):
        """安检 — 需要排队服务"""
        self.wait_time += 1
        self.total_wait_time += 1

    def _handle_gate(self, simulation):
        """过闸机 — 需要排队服务"""
        self.wait_time += 1
        self.total_wait_time += 1

    def _handle_walking(self, simulation):
        """在通道/楼梯/扶梯中行走"""
        self.move(simulation)

    def _handle_waiting(self, simulation):
        """站台候车 — 等待列车到达"""
        self.wait_time += 1
        self.total_wait_time += 1
        # 实际上车由 simulation_engine 的列车管理决定
        # 乘客在此状态表示已在站台排队候车

    def _handle_boarding(self, simulation):
        """上车过程"""
        self.wait_time += 1
        if self.wait_time >= 3:  # 上车约3秒
            self.wait_time = 0
            self.current_state = self.STATE_RIDING

    def _handle_riding(self, simulation):
        """乘车中 — 简化版：乘车一段时间后自动到达目的站台并出站"""
        self.wait_time += 1
        # 乘车约 60~180 秒后到达
        ride_duration = getattr(self, '_ride_duration', None)
        if ride_duration is None:
            self._ride_duration = max(30, int(np.random.poisson(90)))
            ride_duration = self._ride_duration

        if self.wait_time >= ride_duration:
            self.wait_time = 0
            # 到达目的站台，直接转为出站状态
            exits = simulation.station_graph.get_nodes_by_type('exit')
            if exits:
                self.end_node = random.choice(exits)
                self.current_node = self.end_node
                self.current_state = self.STATE_EXITING
                self.path = [self.current_node]
                self.path_index = 0

    def _handle_exiting(self, simulation):
        """出站 — 向出口移动"""
        self.move(simulation)
        # 如果已到达出口节点（当前节点就是路径终点或end_node）
        if self.current_node == self.end_node or self.path_index >= len(self.path) - 1:
            self.wait_time += 1
            if self.wait_time >= 2:  # 出站约2秒
                simulation.remove_passenger(self)

    # ── 移动逻辑 ──────────────────────────────

    def move(self, simulation):
        """在节点间移动"""
        if not self.path or self.path_index >= len(self.path) - 1:
            return

        current = self.path[self.path_index]
        next_node = self.path[self.path_index + 1]

        edge = simulation.station_graph.get_edge(current, next_node)
        if not edge:
            return

        # 获取当前节点信息
        node_info = simulation.station_graph.get_node(current)
        next_info = simulation.station_graph.get_node(next_node)
        density = node_info.get('current_density', 0.0) if node_info else 0.0
        base_speed = node_info.get('base_speed', 1.0) if node_info else 1.0

        # 速度因子（基于密度）
        speed_factor = self._get_speed_factor(density)

        # ── 楼梯/扶梯速度差异化 ──
        cur_type = node_info.get('type', '') if node_info else ''
        next_type = next_info.get('type', '') if next_info else ''
        cur_floor = node_info.get('floor', 0) if node_info else 0
        next_floor = next_info.get('floor', 0) if next_info else 0
        going_up = next_floor > cur_floor
        going_down = next_floor < cur_floor

        stair_escalator_factor = 1.0
        # 楼梯：上楼慢（0.5），下楼稍快（0.7）
        if cur_type == 'stairs' or next_type == 'stairs':
            if going_up:
                stair_escalator_factor = 0.5
            elif going_down:
                stair_escalator_factor = 0.7
            else:
                stair_escalator_factor = 0.6
        # 扶梯：速度较均匀，但上行比下行略慢
        elif cur_type == 'escalator' or next_type == 'escalator':
            if going_up:
                stair_escalator_factor = 0.8
            elif going_down:
                stair_escalator_factor = 0.9
            else:
                stair_escalator_factor = 0.85

        # ── 对向冲突减速 ──
        counter_flow_factor = 1.0
        reverse_count = simulation._edge_directional_count.get((next_node, current), 0)
        if reverse_count > 0:
            forward_count = simulation._edge_directional_count.get((current, next_node), 0)
            if forward_count > 0:
                # 对向比例越高，减速越明显
                ratio = reverse_count / (forward_count + reverse_count)
                counter_flow_factor = max(0.4, 1.0 - ratio * 0.6)

        v_eff = min(self.speed * speed_factor * stair_escalator_factor
                    * counter_flow_factor, base_speed)

        # 移动进度增量
        distance = edge.get('distance', 1.0)
        delta = v_eff / max(distance, 0.5)
        self.move_progress += delta

        if self.move_progress >= 1.0:
            if self._can_move_to(next_node, simulation):
                self.current_node = next_node
                self.path_index += 1
                self.move_progress = 0.0
                self.blocked_time = 0

                # 到达新节点后，根据节点类型切换状态
                self._on_arrive_at_node(next_node, simulation)
            else:
                self.blocked_time += 1
                # 耐心高的乘客在阻塞严重时重规划
                if (self.blocked_time > 5 and
                    self.patience > 0.5 and
                    simulation.current_time - self._last_replan > self._replan_cooldown):
                    self._replan_path(simulation)

    def _can_move_to(self, next_node, simulation) -> bool:
        """检查是否可以移动到目标节点

        使用密度限制：节点人数 <= 面积 × 最大密度(5人/m²)
        服务节点允许排队，上限更宽松
        """
        node_info = simulation.station_graph.get_node(next_node)
        if not node_info:
            return True

        count = simulation.node_passenger_count.get(next_node, 0)
        area = node_info.get('area', 100.0)
        node_type = node_info['type']

        # 密度限制：服务节点允许更高密度（排队）
        if node_type in ('ticket', 'security', 'gate'):
            max_density = 8.0  # 排队区可较拥挤
        else:
            max_density = 5.0  # 一般区域

        if count >= area * max_density:
            return False

        # 边容量检查（基于通行能力，更宽松）
        current = self.current_node
        edge = simulation.station_graph.get_edge(current, next_node)
        if edge:
            edge_count = simulation.edge_passenger_count.get((current, next_node), 0)
            width = edge.get('width', 2.0)
            distance = edge.get('distance', 10.0)
            # 边通行能力 ≈ 宽度 × 距离 / 人均占用空间
            # 一人约占 0.5m × 0.5m = 0.25m²，边面积 = width × distance
            edge_area = width * distance
            edge_cap = max(20, edge_area / 0.5)  # 每0.5m²可站1人，至少20人
            if edge_count >= edge_cap:
                return False

        return True

    def _on_arrive_at_node(self, node_id, simulation):
        """到达节点后的状态转换"""
        node_info = simulation.station_graph.get_node(node_id)
        if not node_info:
            return

        node_type = node_info['type']

        if node_type == 'ticket':
            if not self.has_ticket:
                # 无票乘客到达售票区：
                # 熟悉度高的乘客更可能知道可以扫码/刷卡过闸，跳过售票
                # 基础跳过概率 40% + 熟悉度 × 40%（最高 80%）
                skip_prob = 0.4 + 0.4 * self.familiarity
                if random.random() < skip_prob:
                    # 选择去闸机扫码/现场购票，跳过售票区
                    self.current_state = self.STATE_WALKING
                else:
                    # 去售票机/窗口排队购票
                    self.current_state = self.STATE_TICKET
                    self.wait_time = 0
            else:
                # 有实体票/交通卡/手机支付已准备好，直接过
                self.current_state = self.STATE_WALKING
        elif node_type == 'security':
            self.current_state = self.STATE_SECURITY
            self.wait_time = 0
        elif node_type == 'gate':
            self.current_state = self.STATE_GATE
            self.wait_time = 0
        elif node_type == 'platform':
            self.current_state = self.STATE_WAITING
            self.wait_time = 0
        elif node_type == 'exit':
            self.current_state = self.STATE_EXITING
            self.wait_time = 0
        elif node_type in ('corridor', 'stairs', 'escalator', 'entrance'):
            self.current_state = self.STATE_WALKING

    def _get_speed_factor(self, density: float) -> float:
        """Weidmann 行人速度-密度模型（连续版）"""
        if density < 0.3:
            return 1.0
        if density < 0.8:
            return 1.0 - 0.15 * (density - 0.3) / 0.5
        if density < 2.0:
            return 0.85 - 0.35 * (density - 0.8) / 1.2
        if density < 4.0:
            return 0.50 - 0.30 * (density - 2.0) / 2.0
        if density < 6.0:
            return 0.20 - 0.10 * (density - 4.0) / 2.0
        return 0.10

    def _replan_path(self, simulation):
        """重新规划路径"""
        new_path = simulation.path_planner.find_path(
            self.current_node, self.end_node, mode='multi_objective')
        if new_path and len(new_path) > 1:
            # 保持当前位置，但更新后续路径
            if self.current_node in new_path:
                idx = new_path.index(self.current_node)
                self.path = new_path[idx:]
                self.path_index = 0
                self.move_progress = 0.0
                self.blocked_time = 0
                self._last_replan = simulation.current_time

    def get_state(self):
        return self.current_state

    def get_current_node(self):
        return self.current_node


# ─────────────────────────────────────────
#  乘客生成器
# ─────────────────────────────────────────

class PassengerGenerator:
    """基于泊松到达和时段分布的乘客生成器"""

    def __init__(self, station_graph):
        self.station_graph = station_graph
        self.passenger_id = 0
        self._entry_weights = None

    def _get_entry_weights(self, entry_nodes):
        """幂律权重：主入口流量更大"""
        if self._entry_weights is None or len(self._entry_weights) != len(entry_nodes):
            w = np.array([1.0 / ((i + 1) ** 0.6) for i in range(len(entry_nodes))], dtype=float)
            self._entry_weights = w / w.sum()
        return self._entry_weights

    def generate_passenger(self, time_sec, has_ticket_prob=0.6):
        """生成单个乘客"""
        entry_nodes = self.station_graph.get_nodes_by_type('entrance')
        exit_nodes = self.station_graph.get_nodes_by_type('exit')
        if not entry_nodes or not exit_nodes:
            return None

        weights = self._get_entry_weights(entry_nodes)
        start_node = str(np.random.choice(entry_nodes, p=weights))
        end_node = str(random.choice(exit_nodes))

        # 避免起点=终点（理论上不应该，但以防万一）
        if start_node == end_node:
            return None

        # 速度：正态分布，平均1.2 m/s，标准差0.2
        speed = float(np.clip(np.random.normal(1.2, 0.2), 0.5, 2.0))
        patience = float(np.clip(np.random.beta(2, 2), 0.1, 0.9))
        familiarity = float(np.clip(np.random.beta(2, 3), 0.05, 0.95))

        # 路径策略根据熟悉度选择
        if familiarity > 0.7:
            path_strategy = 'shortest_time'
        elif familiarity > 0.4:
            path_strategy = 'multi_objective'
        elif patience > 0.6:
            path_strategy = 'least_congested'
        else:
            path_strategy = 'shortest_distance'

        has_ticket = random.random() < has_ticket_prob

        self.passenger_id += 1
        return Passenger(
            self.passenger_id, start_node, end_node,
            speed, patience, familiarity, path_strategy, has_ticket
        )

    def generate_passengers(self, time_sec, rate):
        """按泊松分布生成一批乘客"""
        if rate <= 0:
            return []
        count = int(np.random.poisson(rate))
        result = []
        for _ in range(count):
            p = self.generate_passenger(time_sec)
            if p:
                result.append(p)
        return result
