import random
import math

class Passenger:
    """乘客对象"""
    
    # 状态定义
    STATE_ENTERING = 'entering'      # 进站
    STATE_TICKET = 'ticket'          # 购票
    STATE_SECURITY = 'security'      # 安检
    STATE_GATE = 'gate'              # 闸机
    STATE_WAITING = 'waiting'        # 候车
    STATE_RIDING = 'riding'          # 乘车
    STATE_EXITING = 'exiting'        # 出站
    
    def __init__(self, passenger_id, start_node, end_node, speed=1.0, patience=0.5, familiarity=0.5, path_strategy='shortest_time'):
        """初始化乘客
        
        Args:
            passenger_id: 乘客ID
            start_node: 起点节点
            end_node: 终点节点
            speed: 行走速度
            patience: 耐心度（0-1）
            familiarity: 熟悉度（0-1）
            path_strategy: 路径策略
        """
        self.passenger_id = passenger_id
        self.start_node = start_node
        self.end_node = end_node
        self.speed = speed
        self.patience = patience
        self.familiarity = familiarity
        self.path_strategy = path_strategy
        self.current_node = start_node
        self.current_state = self.STATE_ENTERING
        self.wait_time = 0
        self.path = []
        self.path_index = 0
        self.move_progress = 0
        self.blocked_time = 0
    
    def set_path(self, path):
        """设置路径"""
        self.path = path
        self.path_index = 0
        self.move_progress = 0
    
    def update_state(self, simulation):
        """更新乘客状态
        
        Args:
            simulation: 仿真引擎
        """
        if self.current_state == self.STATE_ENTERING:
            self._handle_entering(simulation)
        elif self.current_state == self.STATE_TICKET:
            self._handle_ticket(simulation)
        elif self.current_state == self.STATE_SECURITY:
            self._handle_security(simulation)
        elif self.current_state == self.STATE_GATE:
            self._handle_gate(simulation)
        elif self.current_state == self.STATE_WAITING:
            self._handle_waiting(simulation)
        elif self.current_state == self.STATE_RIDING:
            self._handle_riding(simulation)
        elif self.current_state == self.STATE_EXITING:
            self._handle_exiting(simulation)
    
    def _handle_entering(self, simulation):
        """处理进站状态"""
        # 进站后前往购票
        self.current_state = self.STATE_TICKET
    
    def _handle_ticket(self, simulation):
        """处理购票状态"""
        # 模拟购票时间，考虑队列长度和服务率
        queue_length = len(simulation.queues.get(self.current_node, []))
        service_rate = simulation.service_rates.get('ticket', 0.3)  # 约3秒/人
        
        # 基础购票时间（包含随机性和熟悉度影响）
        base_time = 2 + random.uniform(0, 2)  # 2-4秒
        # 熟悉度越高，操作越快
        base_time *= (1 - self.familiarity * 0.3)  # 最多减少30%时间
        
        # 队列等待时间
        queue_time = queue_length * (1/service_rate)
        
        # 总等待时间
        total_time = base_time + queue_time
        
        # 累积等待时间
        self.wait_time += 1
        
        # 当累积等待时间达到总等待时间时，进入下一状态
        if self.wait_time >= total_time:
            self.wait_time = 0
            self.current_state = self.STATE_SECURITY
    
    def _handle_security(self, simulation):
        """处理安检状态"""
        # 模拟安检时间，考虑队列长度和服务率
        queue_length = len(simulation.queues.get(self.current_node, []))
        service_rate = simulation.service_rates.get('security', 0.2)  # 约5秒/人
        
        # 基础安检时间（包含随机性）
        base_time = 4 + random.uniform(0, 3)  # 4-7秒
        
        # 队列等待时间
        queue_time = queue_length * (1/service_rate)
        
        # 总等待时间
        total_time = base_time + queue_time
        
        # 累积等待时间
        self.wait_time += 1
        
        # 当累积等待时间达到总等待时间时，进入下一状态
        if self.wait_time >= total_time:
            self.wait_time = 0
            self.current_state = self.STATE_GATE
    
    def _handle_gate(self, simulation):
        """处理闸机状态"""
        # 模拟闸机时间，考虑队列长度和服务率
        queue_length = len(simulation.queues.get(self.current_node, []))
        service_rate = simulation.service_rates.get('gate', 0.5)  # 约2秒/人
        
        # 基础闸机时间（包含随机性和熟悉度影响）
        base_time = 1.5 + random.uniform(0, 1)  # 1.5-2.5秒
        # 熟悉度越高，操作越快
        base_time *= (1 - self.familiarity * 0.4)  # 最多减少40%时间
        
        # 队列等待时间
        queue_time = queue_length * (1/service_rate)
        
        # 总等待时间
        total_time = base_time + queue_time
        
        # 累积等待时间
        self.wait_time += 1
        
        # 当累积等待时间达到总等待时间时，进入下一状态
        if self.wait_time >= total_time:
            self.wait_time = 0
            self.current_state = self.STATE_WAITING
    
    def _handle_waiting(self, simulation):
        """处理候车状态"""
        # 模拟候车时间，考虑列车间隔
        # 假设列车间隔为2-5分钟（转换为时间步）
        train_interval = random.uniform(120, 300) / 10  # 12-30时间步
        
        # 累积等待时间
        self.wait_time += 1
        
        # 当累积等待时间达到列车间隔时，进入下一状态
        if self.wait_time >= train_interval:
            self.wait_time = 0
            self.current_state = self.STATE_RIDING
    
    def _handle_riding(self, simulation):
        """处理乘车状态"""
        # 模拟乘车时间，考虑距离和速度
        # 假设乘车时间为1-3分钟（转换为时间步）
        riding_time = random.uniform(60, 180) / 10  # 6-18时间步
        
        # 累积等待时间
        self.wait_time += 1
        
        # 当累积等待时间达到乘车时间时，进入下一状态
        if self.wait_time >= riding_time:
            self.wait_time = 0
            self.current_state = self.STATE_EXITING
    
    def _handle_exiting(self, simulation):
        """处理出站状态"""
        # 模拟出站时间，考虑熟悉度
        base_time = 1.5 + random.uniform(0, 1)  # 1.5-2.5秒
        # 熟悉度越高，操作越快
        base_time *= (1 - self.familiarity * 0.3)  # 最多减少30%时间
        
        # 累积等待时间
        self.wait_time += 1
        
        # 当累积等待时间达到出站时间时，离开系统
        if self.wait_time >= base_time:
            self.wait_time = 0
            # 乘客离开系统
            simulation.remove_passenger(self)
    
    def move(self, simulation):
        """移动乘客
        
        Args:
            simulation: 仿真引擎
        """
        if self.path and self.path_index < len(self.path) - 1:
            current_node = self.path[self.path_index]
            next_node = self.path[self.path_index + 1]
            edge = simulation.station_graph.get_edge(current_node, next_node)
            
            if edge:
                # 计算有效速度
                node_info = simulation.station_graph.get_node(current_node)
                v_node = node_info['base_speed'] * self._get_speed_factor(node_info['current_density'])
                v_eff = min(self.speed, v_node)
                
                # 计算移动进度
                distance = edge['distance']
                dt = 1.0  # 时间步长
                delta_progress = (v_eff * dt) / distance
                self.move_progress += delta_progress
                
                # 检查是否到达下一个节点
                if self.move_progress >= 1.0:
                    # 检查目标节点是否可以进入
                    if self._can_move_to(next_node, simulation):
                        self.current_node = next_node
                        self.path_index += 1
                        self.move_progress = 0
                        self.blocked_time = 0
                    else:
                        # 被阻塞
                        self.blocked_time += 1
                        # 如果阻塞时间过长且有耐心，考虑重新规划路径
                        if self.blocked_time > 5 and self.patience > 0.5:
                            self._replan_path(simulation)
    
    def _can_move_to(self, next_node, simulation):
        """检查是否可以移动到下一个节点
        
        Args:
            next_node: 下一个节点
            simulation: 仿真引擎
        """
        # 检查目标节点是否拥挤
        node_info = simulation.station_graph.get_node(next_node)
        if node_info:
            # 计算当前节点的乘客数量
            node_count = sum(1 for p in simulation.passengers if p.current_node == next_node)
            if node_count >= node_info['capacity']:
                return False
        # 检查路径是否被阻挡
        return True
    
    def _get_speed_factor(self, density):
        """根据密度获取速度因子"""
        if density < 0.5:
            return 1.0
        elif 0.5 <= density < 1.0:
            return 0.85
        elif 1.0 <= density < 2.0:
            return 0.65
        elif 2.0 <= density < 3.0:
            return 0.40
        else:
            return 0.15
    
    def _replan_path(self, simulation):
        """重新规划路径"""
        new_path = simulation.path_planner.find_path(self.current_node, self.end_node, mode='multi_objective')
        if new_path:
            self.set_path(new_path)
    
    def get_state(self):
        """获取当前状态"""
        return self.current_state
    
    def get_current_node(self):
        """获取当前节点"""
        return self.current_node

class PassengerGenerator:
    """乘客生成器"""
    
    def __init__(self, station_graph):
        """初始化乘客生成器
        
        Args:
            station_graph: 地铁站图
        """
        self.station_graph = station_graph
        self.passenger_id = 0
    
    def generate_passenger(self, time):
        """生成乘客
        
        Args:
            time: 当前时间
        """
        # 获取所有入口和出口节点
        entry_nodes = self.station_graph.get_nodes_by_type('entrance')
        exit_nodes = self.station_graph.get_nodes_by_type('exit')
        
        if not entry_nodes or not exit_nodes:
            return None
        
        # 随机选择起点和终点
        start_node = random.choice(entry_nodes)
        end_node = random.choice(exit_nodes)
        
        # 生成乘客属性
        speed = random.uniform(0.8, 1.2)
        patience = random.uniform(0.3, 0.8)
        familiarity = random.uniform(0.2, 1.0)
        
        # 基于熟悉度选择路径策略
        if familiarity > 0.7:
            path_strategy = 'shortest_time'
        elif familiarity > 0.4:
            path_strategy = 'multi_objective'
        else:
            path_strategy = 'shortest_distance'
        
        self.passenger_id += 1
        return Passenger(self.passenger_id, start_node, end_node, speed, patience, familiarity, path_strategy)
    
    def generate_passengers(self, time, rate):
        """生成多个乘客
        
        Args:
            time: 当前时间
            rate: 生成速率（人/秒）
        """
        # 使用泊松过程生成乘客数量
        count = 0
        if rate > 0:
            count = np.random.poisson(rate)
        
        passengers = []
        for _ in range(count):
            passenger = self.generate_passenger(time)
            if passenger:
                passengers.append(passenger)
        return passengers

# 添加numpy导入
import numpy as np