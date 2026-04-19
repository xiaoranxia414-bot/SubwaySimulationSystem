"""仿真配置参数"""
from dataclasses import dataclass, field
from typing import List, Tuple, Dict
import math

@dataclass
class ServiceConfig:
    """服务节点配置"""
    ticket_rate: float = 0.3      # 人/秒 (~3秒/人)
    security_rate: float = 0.2    # 人/秒 (~5秒/人)
    gate_rate: float = 0.5        # 人/秒 (~2秒/人)
    ticket_base_time: Tuple[float, float] = (2.0, 4.0)  # 基础购票时间范围
    security_base_time: Tuple[float, float] = (4.0, 7.0)  # 基础安检时间范围
    gate_base_time: Tuple[float, float] = (1.5, 2.5)  # 基础闸机时间范围

@dataclass
class PassengerConfig:
    """乘客配置"""
    speed_range: Tuple[float, float] = (0.8, 1.2)  # 速度范围
    patience_range: Tuple[float, float] = (0.3, 0.8)  # 耐心度范围
    familiarity_range: Tuple[float, float] = (0.2, 1.0)  # 熟悉度范围
    blocked_threshold: int = 5  # 阻塞超过此时间触发重规划

@dataclass
class CongestionConfig:
    """拥堵配置"""
    node_threshold: float = 2.0  # 节点拥堵阈值
    edge_threshold: float = 2.0  # 边拥堵阈值
    reevaluate_interval: int = 5  # 路径重评估间隔（步）
    reevaluate_cooldown: int = 30  # 同一乘客重评估冷却（步）
    capacity_safety_factor: float = 0.9  # 容量安全系数

@dataclass
class DensitySpeedConfig:
    """密度-速度关系配置（基于行人基本图 Fundamental Diagram）"""
    # 速度因子 = 1 - (density / max_density) ^ gamma
    free_speed: float = 1.2  # 自由流速度 (m/s)
    max_density: float = 5.0  # 最大密度 (人/m²)
    gamma: float = 0.3  # 衰减系数

    def get_speed_factor(self, density: float) -> float:
        """根据密度计算速度因子"""
        if density <= 0:
            return 1.0
        ratio = density / self.max_density
        if ratio >= 1.0:
            return 0.05  # 几乎停滞
        return max(0.05, 1.0 - math.pow(ratio, self.gamma))

@dataclass
class TrainConfig:
    """列车配置"""
    interval_range: Tuple[int, int] = (120, 300)  # 列车间隔（秒）
    dwell_time: Tuple[int, int] = (20, 40)  # 停站时间（秒）
    ride_time: Tuple[int, int] = (60, 180)  # 乘车时间（秒）

@dataclass
class SimulationConfig:
    """仿真全局配置"""
    service: ServiceConfig = field(default_factory=ServiceConfig)
    passenger: PassengerConfig = field(default_factory=PassengerConfig)
    congestion: CongestionConfig = field(default_factory=CongestionConfig)
    density_speed: DensitySpeedConfig = field(default_factory=DensitySpeedConfig)
    train: TrainConfig = field(default_factory=TrainConfig)

    peak_hours: List[Tuple[int, int]] = field(default_factory=lambda: [(7, 9), (17, 19)])
    peak_rate: int = 10  # 高峰期生成速率（人/秒）
    normal_rate: int = 5  # 平峰期生成速率（人/秒）

    # 可配置的服务节点类型
    service_node_types: List[str] = field(default_factory=lambda: ['ticket', 'security', 'gate'])

    spatial_hash_cell_size: float = 1.0
    collision_radius: float = 1.5

    # 统计收集间隔
    stats_interval: int = 10

# 全局默认配置
DEFAULT_CONFIG = SimulationConfig()