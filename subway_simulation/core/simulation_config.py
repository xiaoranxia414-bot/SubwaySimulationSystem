"""仿真配置参数"""
from dataclasses import dataclass, field
from typing import List, Tuple, Dict
import math


@dataclass
class ServiceConfig:
    """服务节点配置"""
    ticket_rate: float = 0.4      # 人/秒 (~2.5秒/人)
    security_rate: float = 0.25   # 人/秒 (~4秒/人)
    gate_rate: float = 0.6        # 人/秒 (~1.7秒/人)
    ticket_base_time: Tuple[float, float] = (2.0, 4.0)
    security_base_time: Tuple[float, float] = (4.0, 7.0)
    gate_base_time: Tuple[float, float] = (1.5, 2.5)


@dataclass
class PassengerConfig:
    """乘客配置"""
    speed_range: Tuple[float, float] = (0.8, 1.5)
    patience_range: Tuple[float, float] = (0.2, 0.9)
    familiarity_range: Tuple[float, float] = (0.1, 0.95)
    blocked_threshold: int = 5
    has_ticket_prob: float = 0.6  # 有票（手机支付/交通卡）概率


@dataclass
class CongestionConfig:
    """拥堵配置"""
    node_threshold: float = 1.0
    edge_threshold: float = 1.5
    reevaluate_interval: int = 5
    reevaluate_cooldown: int = 30
    capacity_safety_factor: float = 0.9


@dataclass
class DensitySpeedConfig:
    """密度-速度关系配置（基于行人基本图）"""
    free_speed: float = 1.2
    max_density: float = 6.0
    gamma: float = 0.3

    def get_speed_factor(self, density: float) -> float:
        if density <= 0:
            return 1.0
        ratio = density / self.max_density
        if ratio >= 1.0:
            return 0.05
        return max(0.05, 1.0 - math.pow(ratio, self.gamma))


@dataclass
class TrainConfig:
    """列车配置"""
    interval_range: Tuple[int, int] = (120, 300)
    dwell_time: Tuple[int, int] = (20, 40)
    ride_time: Tuple[int, int] = (60, 180)
    capacity_range: Tuple[int, int] = (300, 600)


@dataclass
class SimulationConfig:
    """仿真全局配置"""
    service: ServiceConfig = field(default_factory=ServiceConfig)
    passenger: PassengerConfig = field(default_factory=PassengerConfig)
    congestion: CongestionConfig = field(default_factory=CongestionConfig)
    density_speed: DensitySpeedConfig = field(default_factory=DensitySpeedConfig)
    train: TrainConfig = field(default_factory=TrainConfig)

    peak_hours: List[Tuple[int, int]] = field(default_factory=lambda: [(7, 9), (17, 19)])
    base_arrival_rate: float = 2.0  # 基础到达率（人/秒）

    service_node_types: List[str] = field(default_factory=lambda: ['ticket', 'security', 'gate'])
    spatial_hash_cell_size: float = 2.0
    collision_radius: float = 1.5
    stats_interval: int = 10


# 全局默认配置
DEFAULT_CONFIG = SimulationConfig()
