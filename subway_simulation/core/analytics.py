import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from collections import deque

class AnalyticsModule:
    """数据分析模块"""
    
    def __init__(self, station_graph):
        """初始化数据分析模块
        
        Args:
            station_graph: 地铁站图
        """
        self.station_graph = station_graph
        self.data = []
        # 使用环形缓冲区存储最近的时间序列数据
        self.time_series_buffer = deque(maxlen=3600)  # 存储1小时的数据
        # 累计访问量
        self.visit_counts = {}
    
    def record_data(self, time, passengers, densities):
        """记录数据
        
        Args:
            time: 当前时间
            passengers: 乘客列表
            densities: 密度字典
        """
        # 记录每个乘客的状态
        for passenger in passengers:
            self.data.append({
                'time': time,
                'passenger_id': passenger.passenger_id,
                'current_node': passenger.current_node,
                'state': passenger.get_state(),
                'wait_time': passenger.wait_time
            })
            
            # 更新累计访问量
            if passenger.current_node not in self.visit_counts:
                self.visit_counts[passenger.current_node] = 0
            self.visit_counts[passenger.current_node] += 1
        
        # 记录密度数据
        for node_id, density in densities.items():
            self.data.append({
                'time': time,
                'node_id': node_id,
                'density': density,
                'data_type': 'density'
            })
        
        # 更新时间序列缓冲区
        passenger_count = len(passengers)
        avg_density = np.mean(list(densities.values())) if densities else 0
        self.time_series_buffer.append((time, passenger_count, avg_density))
    
    def get_passenger_stats(self):
        """获取乘客统计数据
        
        Returns:
            dict: 乘客统计数据
        """
        # 过滤乘客数据
        passenger_data = [d for d in self.data if 'passenger_id' in d]
        if not passenger_data:
            return None
        
        df = pd.DataFrame(passenger_data)
        stats = {
            'average_wait_time': df['wait_time'].mean(),
            'max_wait_time': df['wait_time'].max(),
            'min_wait_time': df['wait_time'].min(),
            'passenger_count': len(df['passenger_id'].unique()),
            'state_distribution': df['state'].value_counts().to_dict()
        }
        return stats
    
    def get_density_stats(self):
        """获取密度统计数据
        
        Returns:
            dict: 密度统计数据
        """
        # 过滤密度数据
        density_data = [d for d in self.data if 'density' in d]
        if not density_data:
            return None
        
        df = pd.DataFrame(density_data)
        stats = {
            'average_density': df['density'].mean(),
            'max_density': df['density'].max(),
            'min_density': df['density'].min(),
            'congested_nodes': df[df['density'] > 0.8]['node_id'].unique().tolist()
        }
        return stats
    
    def get_time_series_data(self):
        """获取时间序列数据
        
        Returns:
            dict: 时间序列数据
        """
        if not self.time_series_buffer:
            return None
        
        # 从缓冲区提取数据
        times, passenger_counts, avg_densities = zip(*self.time_series_buffer)
        
        return {
            'passenger_count': dict(zip(times, passenger_counts)),
            'average_density': dict(zip(times, avg_densities))
        }
    
    def identify_bottlenecks(self):
        """识别瓶颈
        
        Returns:
            list: 瓶颈节点列表
        """
        # 过滤密度数据
        density_data = [d for d in self.data if 'density' in d]
        if not density_data:
            return []
        
        df = pd.DataFrame(density_data)
        # 计算每个节点的平均密度
        node_avg_density = df.groupby('node_id')['density'].mean()
        # 找出密度大于0.8的节点
        bottlenecks = node_avg_density[node_avg_density > 0.8].index.tolist()
        
        return bottlenecks
    
    def get_top_congested_nodes(self, n=5):
        """获取最拥堵的节点
        
        Args:
            n: 返回数量
        
        Returns:
            list: 最拥堵的节点列表
        """
        density_data = [d for d in self.data if 'density' in d]
        if not density_data:
            return []
        
        df = pd.DataFrame(density_data)
        node_avg_density = df.groupby('node_id')['density'].mean()
        # 按密度降序排序
        sorted_nodes = node_avg_density.sort_values(ascending=False)
        return sorted_nodes.head(n).index.tolist()
    
    def generate_report(self):
        """生成分析报告
        
        Returns:
            dict: 分析报告
        """
        report = {
            'passenger_stats': self.get_passenger_stats(),
            'density_stats': self.get_density_stats(),
            'time_series_data': self.get_time_series_data(),
            'bottlenecks': self.identify_bottlenecks(),
            'top_congested_nodes': self.get_top_congested_nodes(),
            'visit_counts': self.visit_counts
        }
        return report
    
    def plot_passenger_flow(self):
        """绘制乘客流量图"""
        time_series = self.get_time_series_data()
        if not time_series:
            return
        
        plt.figure(figsize=(10, 6))
        plt.plot(list(time_series['passenger_count'].keys()), 
                 list(time_series['passenger_count'].values()))
        plt.title('乘客流量随时间变化')
        plt.xlabel('时间 (秒)')
        plt.ylabel('乘客数量')
        plt.grid(True)
        plt.savefig('passenger_flow.png')
        plt.close()
    
    def plot_density_trend(self):
        """绘制密度趋势图"""
        time_series = self.get_time_series_data()
        if not time_series:
            return
        
        plt.figure(figsize=(10, 6))
        plt.plot(list(time_series['average_density'].keys()), 
                 list(time_series['average_density'].values()))
        plt.title('平均密度随时间变化')
        plt.xlabel('时间 (秒)')
        plt.ylabel('平均密度')
        plt.grid(True)
        plt.savefig('density_trend.png')
        plt.close()
    
    def plot_state_distribution(self):
        """绘制状态分布图"""
        passenger_stats = self.get_passenger_stats()
        if not passenger_stats or 'state_distribution' not in passenger_stats:
            return
        
        state_dist = passenger_stats['state_distribution']
        plt.figure(figsize=(10, 6))
        plt.bar(state_dist.keys(), state_dist.values())
        plt.title('乘客状态分布')
        plt.xlabel('状态')
        plt.ylabel('数量')
        plt.grid(True)
        plt.savefig('state_distribution.png')
        plt.close()
    
    def plot_heatmap(self):
        """绘制热力图"""
        if not self.visit_counts:
            return
        
        # 获取节点坐标
        node_coords = {}
        for node_id, node_data in self.station_graph.get_graph().nodes(data=True):
            node_coords[node_id] = (node_data['x'], node_data['y'])
        
        # 准备热力图数据
        x = []
        y = []
        values = []
        
        for node_id, count in self.visit_counts.items():
            if node_id in node_coords:
                x.append(node_coords[node_id][0])
                y.append(node_coords[node_id][1])
                values.append(count)
        
        plt.figure(figsize=(10, 6))
        scatter = plt.scatter(x, y, c=values, cmap='hot', s=100, alpha=0.7)
        plt.colorbar(scatter, label='累计访问量')
        
        # 添加节点标签
        for node_id, (nx, ny) in node_coords.items():
            plt.text(nx, ny, node_id, ha='center', va='center', fontsize=8, color='white')
        
        plt.title('地铁站热力图')
        plt.xlabel('X坐标')
        plt.ylabel('Y坐标')
        plt.savefig('heatmap.png')
        plt.close()
    
    def clear_data(self):
        """清空数据"""
        self.data.clear()
        self.time_series_buffer.clear()
        self.visit_counts.clear()