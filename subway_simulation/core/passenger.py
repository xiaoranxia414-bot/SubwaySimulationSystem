import random
import math
import numpy as np


class Passenger:
    """乘客对象"""

    STATE_ENTERING = 'entering'
    STATE_TICKET   = 'ticket'
    STATE_SECURITY = 'security'
    STATE_GATE     = 'gate'
    STATE_WAITING  = 'waiting'
    STATE_RIDING   = 'riding'
    STATE_EXITING  = 'exiting'

    def __init__(self, passenger_id, start_node, end_node,
                 speed=1.0, patience=0.5, familiarity=0.5,
                 path_strategy='shortest_time'):
        self.passenger_id    = passenger_id
        self.start_node      = start_node
        self.end_node        = end_node
        self.speed           = speed
        self.patience        = patience
        self.familiarity     = familiarity
        self.path_strategy   = path_strategy
        self.current_node    = start_node
        self.current_state   = self.STATE_ENTERING
        self.wait_time       = 0
        self.total_wait_time = 0   # 只计入真实等待/排队时间，不含骑乘和离站
        self.path            = []
        self.path_index      = 0
        self.move_progress   = 0
        self.blocked_time    = 0

        # [修改] 根据乘客属性随机化各阶段服务时长，避免所有人完全相同
        #   熟悉度高 → 购票/过闸更快；耐心度高 → 愿意多等
        #   使用泊松分布：均值由属性决定，具有自然随机性
        self._ticket_duration   = max(1, int(np.random.poisson(3.0 / (0.5 + familiarity))))
        self._security_duration = max(1, int(np.random.poisson(5.0)))           # 安检时长较固定
        self._gate_duration     = max(1, int(np.random.poisson(2.0 / (0.5 + familiarity * 0.5))))
        self._waiting_duration  = max(1, int(np.random.poisson(10.0)))          # 等候列车，随机波动
        self._riding_duration   = max(5, int(np.random.poisson(20.0)))          # 乘车时长
        self._exiting_duration  = max(1, int(np.random.poisson(2.0)))           # 离站时长

    def set_path(self, path):
        self.path          = path
        self.path_index    = 0
        self.move_progress = 0

    def update_state(self, simulation):
        dispatch = {
            self.STATE_ENTERING:  self._handle_entering,
            self.STATE_TICKET:    self._handle_ticket,
            self.STATE_SECURITY:  self._handle_security,
            self.STATE_GATE:      self._handle_gate,
            self.STATE_WAITING:   self._handle_waiting,
            self.STATE_RIDING:    self._handle_riding,
            self.STATE_EXITING:   self._handle_exiting,
        }
        dispatch.get(self.current_state, lambda s: None)(simulation)

    def _handle_entering(self, simulation):
        self.current_state = self.STATE_TICKET

    def _handle_ticket(self, simulation):
        self.wait_time       += 1
        self.total_wait_time += 1   # 购票排队：计入等待时间
        if self.wait_time >= self._ticket_duration:
            self.wait_time = 0
            self.current_state = self.STATE_SECURITY

    def _handle_security(self, simulation):
        self.wait_time       += 1
        self.total_wait_time += 1   # 安检排队：计入等待时间
        if self.wait_time >= self._security_duration:
            self.wait_time = 0
            self.current_state = self.STATE_GATE

    def _handle_gate(self, simulation):
        self.wait_time       += 1
        self.total_wait_time += 1   # 过闸排队：计入等待时间
        if self.wait_time >= self._gate_duration:
            self.wait_time = 0
            self.current_state = self.STATE_WAITING

    def _handle_waiting(self, simulation):
        self.wait_time       += 1
        self.total_wait_time += 1   # 等候列车：计入等待时间
        if self.wait_time >= self._waiting_duration:
            self.wait_time = 0
            self.current_state = self.STATE_RIDING

    def _handle_riding(self, simulation):
        # [修改] 乘车阶段：不计入 total_wait_time（乘车不是等待）
        self.wait_time += 1
        if self.wait_time >= self._riding_duration:
            self.wait_time = 0
            self.current_state = self.STATE_EXITING

    def _handle_exiting(self, simulation):
        # [修改] 离站阶段：不计入 total_wait_time（离站不是等待）
        self.wait_time += 1
        if self.wait_time >= self._exiting_duration:
            self.wait_time = 0
            simulation.remove_passenger(self)

    def move(self, simulation):
        if not (self.path and self.path_index < len(self.path) - 1):
            return
        current_node = self.path[self.path_index]
        next_node    = self.path[self.path_index + 1]
        edge = simulation.station_graph.get_edge(current_node, next_node)
        if not edge:
            return

        node_info = simulation.station_graph.get_node(current_node)
        v_node    = node_info['base_speed'] * self._get_speed_factor(node_info['current_density'])
        v_eff     = min(self.speed, v_node)

        norm_dist = min(edge['distance'], 50.0)
        delta     = max((v_eff * 1.0) / norm_dist, 0.2)
        self.move_progress += delta

        if self.move_progress >= 1.0:
            if self._can_move_to(next_node, simulation):
                self.current_node  = next_node
                self.path_index   += 1
                self.move_progress = 0
                self.blocked_time  = 0
            else:
                self.blocked_time += 1
                if self.blocked_time > 5 and self.patience > 0.5:
                    self._replan_path(simulation)

    def _can_move_to(self, next_node, simulation):
        node_info = simulation.station_graph.get_node(next_node)
        if node_info:
            count = simulation.node_passenger_count.get(next_node, 0)
            if count >= node_info['capacity']:
                return False
        return True

    def _get_speed_factor(self, density):
        """Weidmann行人速度-密度模型（简化版）"""
        if density < 0.5: return 1.0
        if density < 1.0: return 0.85
        if density < 2.0: return 0.65
        if density < 3.0: return 0.40
        return 0.15

    def _replan_path(self, simulation):
        new_path = simulation.path_planner.find_path(
            self.current_node, self.end_node, mode='multi_objective')
        if new_path:
            self.set_path(new_path)

    def get_state(self):        return self.current_state
    def get_current_node(self): return self.current_node


# ─────────────────────────────────────────────────────────
#  乘客生成器：泊松到达 + 入口权重 + 属性异质性
# ─────────────────────────────────────────────────────────
class PassengerGenerator:
    def __init__(self, station_graph):
        self.station_graph  = station_graph
        self.passenger_id   = 0
        self._entry_weights = None

    def _get_entry_weights(self, entry_nodes):
        """幂律权重：w_i = 1/(i+1)^0.6，主入口流量更大"""
        if self._entry_weights is None or len(self._entry_weights) != len(entry_nodes):
            w = np.array([1.0 / ((i + 1) ** 0.6) for i in range(len(entry_nodes))], dtype=float)
            self._entry_weights = w / w.sum()
        return self._entry_weights

    def generate_passenger(self, time):
        entry_nodes = self.station_graph.get_nodes_by_type('entrance')
        exit_nodes  = self.station_graph.get_nodes_by_type('exit')
        if not entry_nodes or not exit_nodes:
            return None

        weights    = self._get_entry_weights(entry_nodes)
        start_node = str(np.random.choice(entry_nodes, p=weights))
        end_node   = random.choice(exit_nodes)

        speed       = float(np.clip(np.random.normal(1.0, 0.15), 0.5, 1.8))
        patience    = float(np.random.beta(2, 2))
        familiarity = float(np.random.beta(1.5, 3))

        if familiarity > 0.7:
            path_strategy = 'shortest_time'
        elif familiarity > 0.4:
            path_strategy = 'multi_objective'
        else:
            path_strategy = 'shortest_distance'

        self.passenger_id += 1
        return Passenger(self.passenger_id, start_node, end_node,
                         speed, patience, familiarity, path_strategy)

    def generate_passengers(self, time, rate):
        if rate <= 0:
            return []
        count = int(np.random.poisson(rate))
        result = []
        for _ in range(count):
            p = self.generate_passenger(time)
            if p:
                result.append(p)
        return result