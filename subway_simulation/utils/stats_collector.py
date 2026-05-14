import numpy as np
from collections import defaultdict, deque
from typing import Dict, List, Optional


class StatsCollector:
    """统计数据收集器 — 使用动态数据结构，支持大规模仿真"""

    def __init__(self, max_history_steps=10000):
        self.max_history_steps = max_history_steps

        # 乘客状态历史：按时间步存储
        self.passenger_history = []  # [(time, passenger_id, node, state, wait_time), ...]

        # 区域密度历史
        self.density_history = []  # [(time, node_id, density), ...]

        # 队列长度历史
        self.queue_history = []  # [(time, node_id, length), ...]

        # 列车状态历史
        self.train_history = []  # [(time, line_id, is_at_station, boarded), ...]

        # 当前步的聚合数据
        self.current_step = 0
        self.area_density = {}
        self.queue_lengths = {}
        self.train_status = {}

        # 用于快速统计的索引
        self._step_passenger_counts = defaultdict(int)
        self._step_state_counts = defaultdict(lambda: defaultdict(int))

    def record_passenger_state(self, passenger_id, time, location, state, wait_time):
        """记录乘客状态"""
        self.passenger_history.append((time, passenger_id, location, state, wait_time))
        self._step_passenger_counts[time] += 1
        self._step_state_counts[time][state] += 1

    def update_area_density(self, area_id, density):
        """更新区域密度"""
        self.area_density[area_id] = density
        self.density_history.append((self.current_step, area_id, density))

    def update_queue_length(self, queue_id, length):
        """更新队列长度"""
        self.queue_lengths[queue_id] = length
        self.queue_history.append((self.current_step, queue_id, length))

    def update_train_status(self, line_id, is_at_station, boarded_passengers):
        """更新列车状态"""
        self.train_status[line_id] = {
            'is_at_station': is_at_station,
            'boarded': boarded_passengers,
        }
        self.train_history.append(
            (self.current_step, line_id, is_at_station, boarded_passengers))

    def get_passenger_stats(self) -> Optional[Dict]:
        """获取乘客统计"""
        if not self.passenger_history:
            return None

        # 提取当前步的数据
        current_data = [h for h in self.passenger_history if h[0] == self.current_step]
        if not current_data:
            # 回退到最近有数据的时间步
            last_time = self.passenger_history[-1][0]
            current_data = [h for h in self.passenger_history if h[0] == last_time]

        if not current_data:
            return None

        wait_times = [h[4] for h in current_data]
        states = [h[3] for h in current_data]
        unique_ids = set(h[1] for h in current_data)

        state_dist = {}
        for s in states:
            state_dist[s] = state_dist.get(s, 0) + 1

        return {
            'average_wait_time': round(sum(wait_times) / len(wait_times), 2) if wait_times else 0,
            'max_wait_time': max(wait_times) if wait_times else 0,
            'min_wait_time': min(wait_times) if wait_times else 0,
            'passenger_count': len(unique_ids),
            'state_distribution': state_dist,
        }

    def get_area_density_stats(self) -> Optional[Dict]:
        """获取区域密度统计"""
        if not self.area_density:
            return None

        densities = list(self.area_density.values())
        return {
            'average_density': round(sum(densities) / len(densities), 4) if densities else 0,
            'max_density': round(max(densities), 4) if densities else 0,
            'min_density': round(min(densities), 4) if densities else 0,
            'congested_areas': [area for area, d in self.area_density.items() if d > 1.0],
        }

    def get_queue_stats(self) -> Optional[Dict]:
        """获取队列统计"""
        if not self.queue_lengths:
            return None

        lengths = list(self.queue_lengths.values())
        return {
            'average_queue_length': round(sum(lengths) / len(lengths), 2) if lengths else 0,
            'max_queue_length': max(lengths) if lengths else 0,
            'min_queue_length': min(lengths) if lengths else 0,
            'total_queues': len(lengths),
        }

    def get_train_stats(self) -> Optional[Dict]:
        """获取列车统计"""
        if not self.train_status:
            return None

        at_station_count = sum(1 for t in self.train_status.values() if t['is_at_station'])
        total_boarded = sum(t['boarded'] for t in self.train_status.values())

        return {
            'total_trains': len(self.train_status),
            'trains_at_station': at_station_count,
            'total_boarded': total_boarded,
        }

    def get_time_series(self) -> Dict:
        """获取时间序列数据"""
        # 按时间步聚合乘客数量
        time_counts = defaultdict(int)
        for time, pid, loc, state, wait in self.passenger_history:
            time_counts[time] += 1

        times = sorted(time_counts.keys())
        return {
            'times': times,
            'passenger_counts': [time_counts[t] for t in times],
        }

    def get_bottleneck_analysis(self, top_n=5) -> List:
        """分析常发性拥堵点"""
        if not self.density_history:
            return []

        # 计算每个节点的平均密度和超过阈值的比例
        node_stats = defaultdict(lambda: {'sum': 0, 'count': 0, 'high_count': 0})
        for time, node_id, density in self.density_history:
            node_stats[node_id]['sum'] += density
            node_stats[node_id]['count'] += 1
            if density > 1.0:
                node_stats[node_id]['high_count'] += 1

        results = []
        for node_id, stats in node_stats.items():
            avg = stats['sum'] / stats['count'] if stats['count'] > 0 else 0
            ratio = stats['high_count'] / stats['count'] if stats['count'] > 0 else 0
            results.append({
                'node_id': node_id,
                'avg_density': round(avg, 4),
                'high_density_ratio': round(ratio, 4),
                'high_count': stats['high_count'],
            })

        results.sort(key=lambda x: x['avg_density'], reverse=True)
        return results[:top_n]

    def clear(self):
        self.passenger_history.clear()
        self.density_history.clear()
        self.queue_history.clear()
        self.train_history.clear()
        self.current_step = 0
        self.area_density.clear()
        self.queue_lengths.clear()
        self.train_status.clear()
        self._step_passenger_counts.clear()
        self._step_state_counts.clear()

    def next_step(self):
        self.current_step += 1
        self.area_density.clear()
        self.queue_lengths.clear()
        self.train_status.clear()

        # 限制历史数据大小
        if len(self.passenger_history) > self.max_history_steps * 10:
            self.passenger_history = self.passenger_history[-self.max_history_steps * 5:]
        if len(self.density_history) > self.max_history_steps * 5:
            self.density_history = self.density_history[-self.max_history_steps * 2:]
