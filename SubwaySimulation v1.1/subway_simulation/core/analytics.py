import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from collections import deque


class AnalyticsModule:
    """数据分析模块"""

    def __init__(self, station_graph):
        self.station_graph = station_graph
        self.data = []
        self.time_series_buffer = deque(maxlen=3600)
        self.visit_counts = {}
        # [修改] 存储已离场乘客的最终等待时间：{passenger_id: final_total_wait_time}
        # 由外部（SubwaySimulation.generate_analytics）从 SimulationEngine 传入
        self._finished_wait_times = {}

    def record_finished_passengers(self, finished_dict: dict):
        """
        [新增] 接收已离场乘客的最终等待时间字典。
        在 generate_report 之前调用，确保已离场乘客被纳入统计。

        Args:
            finished_dict: {passenger_id: final_total_wait_time}，
                           由 SimulationEngine.finished_wait_times 提供
        """
        self._finished_wait_times.update(finished_dict)

    def record_data(self, time, passengers, densities):
        for passenger in passengers:
            pid = passenger.passenger_id
            self.data.append({
                'time':            time,
                'passenger_id':    pid,
                'current_node':    passenger.current_node,
                'state':           passenger.get_state(),
                'total_wait_time': passenger.total_wait_time,
            })
            node = passenger.current_node
            self.visit_counts[node] = self.visit_counts.get(node, 0) + 1

        for node_id, density in densities.items():
            self.data.append({
                'time':      time,
                'node_id':   node_id,
                'density':   density,
                'data_type': 'density',
            })

        passenger_count = len(passengers)
        avg_density = np.mean(list(densities.values())) if densities else 0
        self.time_series_buffer.append((time, passenger_count, avg_density))

    def get_passenger_stats(self):
        passenger_data = [d for d in self.data if 'passenger_id' in d]

        if not passenger_data and not self._finished_wait_times:
            return None

        # 从快照取每人最大值，并提取状态分布
        snapshot_per_passenger = {}
        state_dist = {}
        if passenger_data:
            df = pd.DataFrame(passenger_data)
            snapshot_per_passenger = df.groupby('passenger_id')['total_wait_time'].max().to_dict()
            state_dist = df['state'].value_counts().to_dict()

        # 合并两个来源：
        #   快照数据（仍在场乘客的最大快照值）作为基础
        #   _finished_wait_times（已离场乘客的精确最终值）覆盖更新
        merged = dict(snapshot_per_passenger)
        merged.update(self._finished_wait_times)

        if not merged:
            return None

        wait_values = list(merged.values())
        return {
            'average_wait_time':  float(np.mean(wait_values)),
            'max_wait_time':      float(np.max(wait_values)),
            'min_wait_time':      float(np.min(wait_values)),
            'passenger_count':    len(merged),
            'state_distribution': state_dist,
        }

    def get_density_stats(self):
        density_data = [d for d in self.data if 'density' in d]
        if not density_data:
            return None

        df = pd.DataFrame(density_data)
        return {
            'average_density': float(df['density'].mean()),
            'max_density':     float(df['density'].max()),
            'min_density':     float(df['density'].min()),
            'congested_nodes': df[df['density'] > 0.8]['node_id'].unique().tolist(),
        }

    def get_time_series_data(self):
        if not self.time_series_buffer:
            return None
        times, passenger_counts, avg_densities = zip(*self.time_series_buffer)
        return {
            'passenger_count': dict(zip(times, passenger_counts)),
            'average_density': dict(zip(times, avg_densities)),
        }

    def identify_bottlenecks(self):
        density_data = [d for d in self.data if 'density' in d]
        if not density_data:
            return []
        df = pd.DataFrame(density_data)
        node_avg = df.groupby('node_id')['density'].mean()
        return node_avg[node_avg > 0.8].index.tolist()

    def get_top_congested_nodes(self, n=5):
        density_data = [d for d in self.data if 'density' in d]
        if not density_data:
            return [], {}
        df = pd.DataFrame(density_data)
        node_avg = df.groupby('node_id')['density'].mean().sort_values(ascending=False)
        top_nodes   = node_avg.head(n).index.tolist()
        top_density = node_avg.head(n).to_dict()
        return top_nodes, top_density

    def generate_report(self):
        top_nodes, top_density = self.get_top_congested_nodes()
        return {
            'passenger_stats':       self.get_passenger_stats(),
            'density_stats':         self.get_density_stats(),
            'time_series_data':      self.get_time_series_data(),
            'bottlenecks':           self.identify_bottlenecks(),
            'top_congested_nodes':   top_nodes,
            'top_congested_density': top_density,
            'visit_counts':          self.visit_counts,
        }

    def clear_data(self):
        self.data.clear()
        self.time_series_buffer.clear()
        self.visit_counts.clear()
        # [修改] 重置时也清空已离场乘客记录
        self._finished_wait_times.clear()

    # ── 绘图方法（保留，供外部调用）──────────
    def plot_passenger_flow(self):
        ts = self.get_time_series_data()
        if not ts: return
        plt.figure(figsize=(10, 6))
        plt.plot(list(ts['passenger_count'].keys()), list(ts['passenger_count'].values()))
        plt.title('乘客流量随时间变化'); plt.xlabel('时间 (秒)'); plt.ylabel('乘客数量')
        plt.grid(True); plt.savefig('passenger_flow.png'); plt.close()

    def plot_density_trend(self):
        ts = self.get_time_series_data()
        if not ts: return
        plt.figure(figsize=(10, 6))
        plt.plot(list(ts['average_density'].keys()), list(ts['average_density'].values()))
        plt.title('平均密度随时间变化'); plt.xlabel('时间 (秒)'); plt.ylabel('平均密度')
        plt.grid(True); plt.savefig('density_trend.png'); plt.close()

    def plot_heatmap(self):
        if not self.visit_counts: return
        node_coords = {nid: (d['x'], d['y'])
                       for nid, d in self.station_graph.get_graph().nodes(data=True)}
        x, y, vals = [], [], []
        for nid, cnt in self.visit_counts.items():
            if nid in node_coords:
                x.append(node_coords[nid][0]); y.append(node_coords[nid][1]); vals.append(cnt)
        plt.figure(figsize=(10, 6))
        sc = plt.scatter(x, y, c=vals, cmap='hot', s=100, alpha=0.7)
        plt.colorbar(sc, label='累计访问量')
        for nid, (nx, ny) in node_coords.items():
            plt.text(nx, ny, nid, ha='center', va='center', fontsize=8, color='white')
        plt.title('地铁站热力图'); plt.savefig('heatmap.png'); plt.close()