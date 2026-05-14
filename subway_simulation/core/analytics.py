import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from collections import deque, defaultdict
from typing import Dict, List, Optional


class AnalyticsModule:
    """数据分析模块 — 实时收集、统计、可视化"""

    def __init__(self, station_graph):
        self.station_graph = station_graph
        self.data = []
        self.time_series_buffer = deque(maxlen=7200)  # 存储2小时数据
        self.visit_counts = defaultdict(int)
        self.node_density_history = defaultdict(list)  # node_id -> [(time, density), ...]
        self.passenger_flow_history = []  # [(time, in_count, out_count), ...]

    def record_data(self, time, passengers, densities):
        """记录数据"""
        in_count = 0
        out_count = 0

        for passenger in passengers:
            self.data.append({
                'time': time,
                'passenger_id': passenger.passenger_id,
                'current_node': passenger.current_node,
                'state': passenger.get_state(),
                'wait_time': passenger.total_wait_time,
            })
            self.visit_counts[passenger.current_node] += 1

            if passenger.get_state() == 'entering':
                in_count += 1

        for node_id, density in densities.items():
            self.data.append({
                'time': time,
                'node_id': node_id,
                'density': density,
                'data_type': 'density',
            })
            self.node_density_history[node_id].append((time, density))

        passenger_count = len(passengers)
        avg_density = np.mean(list(densities.values())) if densities else 0
        self.time_series_buffer.append((time, passenger_count, avg_density, in_count, out_count))
        self.passenger_flow_history.append((time, in_count, out_count))

    def get_passenger_stats(self) -> Optional[Dict]:
        """获取乘客统计数据"""
        passenger_data = [d for d in self.data if 'passenger_id' in d]
        if not passenger_data:
            return None

        df = pd.DataFrame(passenger_data)
        stats = {
            'average_wait_time': round(df['wait_time'].mean(), 2),
            'max_wait_time': round(df['wait_time'].max(), 2),
            'min_wait_time': round(df['wait_time'].min(), 2),
            'passenger_count': int(df['passenger_id'].nunique()),
            'state_distribution': df['state'].value_counts().to_dict(),
        }
        return stats

    def get_density_stats(self) -> Optional[Dict]:
        """获取密度统计数据"""
        density_data = [d for d in self.data if 'density' in d]
        if not density_data:
            return None

        df = pd.DataFrame(density_data)
        stats = {
            'average_density': round(df['density'].mean(), 4),
            'max_density': round(df['density'].max(), 4),
            'min_density': round(df['density'].min(), 4),
            'congested_nodes': df[df['density'] > 1.0]['node_id'].unique().tolist(),
        }
        return stats

    def get_time_series_data(self) -> Optional[Dict]:
        """获取时间序列数据"""
        if not self.time_series_buffer:
            return None

        times, counts, densities, ins, outs = zip(*self.time_series_buffer)
        return {
            'times': list(times),
            'passenger_count': dict(zip(times, counts)),
            'average_density': dict(zip(times, densities)),
            'in_count': dict(zip(times, ins)),
            'out_count': dict(zip(times, outs)),
        }

    def identify_bottlenecks(self, threshold=1.0) -> List[Dict]:
        """识别瓶颈节点（基于历史平均密度）"""
        if not self.node_density_history:
            return []

        results = []
        for node_id, history in self.node_density_history.items():
            if not history:
                continue
            densities = [d for _, d in history]
            avg_density = sum(densities) / len(densities)
            high_count = sum(1 for d in densities if d > threshold)
            high_ratio = high_count / len(densities)

            if avg_density > threshold * 0.5 or high_ratio > 0.3:
                results.append({
                    'node_id': node_id,
                    'avg_density': round(avg_density, 4),
                    'high_density_ratio': round(high_ratio, 4),
                    'max_density': round(max(densities), 4),
                    'samples': len(densities),
                })

        results.sort(key=lambda x: x['avg_density'], reverse=True)
        return results

    def get_top_congested_nodes(self, n=5) -> List[Dict]:
        """获取最拥堵的节点"""
        density_data = [d for d in self.data if 'density' in d]
        if not density_data:
            return []

        df = pd.DataFrame(density_data)
        node_avg = df.groupby('node_id')['density'].mean().sort_values(ascending=False)
        return [{'node_id': nid, 'avg_density': round(v, 4)}
                for nid, v in node_avg.head(n).items()]

    def get_node_time_series(self, node_id) -> List:
        """获取指定节点的时间序列密度"""
        return self.node_density_history.get(node_id, [])

    def generate_report(self) -> Dict:
        """生成综合分析报告"""
        report = {
            'passenger_stats': self.get_passenger_stats(),
            'density_stats': self.get_density_stats(),
            'time_series_data': self.get_time_series_data(),
            'bottlenecks': self.identify_bottlenecks(),
            'top_congested_nodes': self.get_top_congested_nodes(),
            'visit_counts': dict(self.visit_counts),
        }
        return report

    # ── 可视化 ──────────────────────────────

    def plot_passenger_flow(self, output_file='passenger_flow.png'):
        """绘制乘客流量图"""
        ts = self.get_time_series_data()
        if not ts:
            return

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

        times = ts['times']
        counts = [ts['passenger_count'].get(t, 0) for t in times]
        densities = [ts['average_density'].get(t, 0) for t in times]

        ax1.plot(times, counts, 'b-', linewidth=1.5, label='乘客数量')
        ax1.set_title('乘客流量随时间变化')
        ax1.set_xlabel('时间 (秒)')
        ax1.set_ylabel('乘客数量')
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        ax2.plot(times, densities, 'r-', linewidth=1.5, label='平均密度')
        ax2.set_title('平均密度随时间变化')
        ax2.set_xlabel('时间 (秒)')
        ax2.set_ylabel('平均密度 (人/m²)')
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        plt.tight_layout()
        plt.savefig(output_file, dpi=150)
        plt.close()

    def plot_density_trend(self, output_file='density_trend.png'):
        """绘制密度趋势图"""
        ts = self.get_time_series_data()
        if not ts:
            return

        plt.figure(figsize=(10, 6))
        times = ts['times']
        densities = [ts['average_density'].get(t, 0) for t in times]
        plt.plot(times, densities, 'g-', linewidth=1.5)
        plt.title('平均密度随时间变化')
        plt.xlabel('时间 (秒)')
        plt.ylabel('平均密度')
        plt.grid(True, alpha=0.3)
        plt.savefig(output_file, dpi=150)
        plt.close()

    def plot_state_distribution(self, output_file='state_distribution.png'):
        """绘制状态分布图"""
        stats = self.get_passenger_stats()
        if not stats or 'state_distribution' not in stats:
            return

        state_dist = stats['state_distribution']
        plt.figure(figsize=(10, 6))
        colors = plt.cm.Set3(np.linspace(0, 1, len(state_dist)))
        bars = plt.bar(state_dist.keys(), state_dist.values(), color=colors)
        plt.title('乘客状态分布')
        plt.xlabel('状态')
        plt.ylabel('数量')
        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3, axis='y')

        # 添加数值标签
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height,
                     f'{int(height)}', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(output_file, dpi=150)
        plt.close()

    def plot_heatmap(self, output_file='heatmap.png'):
        """绘制客流热力图"""
        if not self.visit_counts:
            return

        node_coords = {}
        for node_id, node_data in self.station_graph.get_graph().nodes(data=True):
            node_coords[node_id] = (node_data['x'], node_data['y'])

        x = []
        y = []
        values = []
        for node_id, count in self.visit_counts.items():
            if node_id in node_coords:
                x.append(node_coords[node_id][0])
                y.append(node_coords[node_id][1])
                values.append(count)

        plt.figure(figsize=(12, 8))
        scatter = plt.scatter(x, y, c=values, cmap='YlOrRd', s=300, alpha=0.8, edgecolors='black')
        plt.colorbar(scatter, label='累计访问量')

        for node_id, (nx, ny) in node_coords.items():
            plt.text(nx, ny, node_id, ha='center', va='center',
                     fontsize=8, fontweight='bold', color='black')

        plt.title('地铁站客流热力图')
        plt.xlabel('X坐标')
        plt.ylabel('Y坐标')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_file, dpi=150)
        plt.close()

    def plot_bottleneck_analysis(self, output_file='bottleneck_analysis.png'):
        """绘制瓶颈分析图"""
        bottlenecks = self.identify_bottlenecks()
        if not bottlenecks:
            return

        plt.figure(figsize=(12, 6))
        nodes = [b['node_id'] for b in bottlenecks[:10]]
        avg_densities = [b['avg_density'] for b in bottlenecks[:10]]
        high_ratios = [b['high_density_ratio'] * 100 for b in bottlenecks[:10]]

        x = np.arange(len(nodes))
        width = 0.35

        plt.bar(x - width/2, avg_densities, width, label='平均密度', color='coral')
        plt.bar(x + width/2, high_ratios, width, label='高密度占比(%)', color='skyblue')

        plt.xlabel('节点')
        plt.ylabel('数值')
        plt.title('瓶颈节点分析')
        plt.xticks(x, nodes, rotation=45)
        plt.legend()
        plt.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        plt.savefig(output_file, dpi=150)
        plt.close()

    def clear_data(self):
        self.data.clear()
        self.time_series_buffer.clear()
        self.visit_counts.clear()
        self.node_density_history.clear()
        self.passenger_flow_history.clear()
