import pandas as pd
import numpy as np

class StatsCollector:
    """统计数据收集器"""
    
    def __init__(self, max_passengers=1000, max_steps=1000):
        """初始化统计数据收集器
        
        Args:
            max_passengers: 最大乘客数量
            max_steps: 最大步数
        """
        # 使用NumPy数组存储乘客状态
        self.data = np.zeros((max_steps, max_passengers), dtype=[
            ('passenger_id', 'i4'),
            ('time', 'i4'),
            ('location', 'U50'),
            ('state', 'U20'),
            ('wait_time', 'f4')
        ])
        self.current_step = 0
        self.max_passengers = max_passengers
        self.max_steps = max_steps
        
        self.area_density = {}
        self.queue_lengths = {}
    
    def record_passenger_state(self, passenger_id, time, location, state, wait_time):
        """记录乘客状态"""
        if self.current_step < self.max_steps:
            # 找到第一个空槽位
            for i in range(self.max_passengers):
                if self.data[self.current_step, i]['passenger_id'] == 0:
                    self.data[self.current_step, i] = (
                        passenger_id, time, location, state, wait_time
                    )
                    break
    
    def update_area_density(self, area_id, density):
        """更新区域密度"""
        self.area_density[area_id] = density
    
    def update_queue_length(self, queue_id, length):
        """更新队列长度"""
        self.queue_lengths[queue_id] = length
    
    def get_passenger_stats(self):
        """获取乘客统计数据"""
        # 提取非零数据
        valid_data = self.data[self.data['passenger_id'] != 0]
        if valid_data.size == 0:
            return None
        
        df = pd.DataFrame(valid_data)
        stats = {
            'average_wait_time': df['wait_time'].mean(),
            'max_wait_time': df['wait_time'].max(),
            'min_wait_time': df['wait_time'].min(),
            'passenger_count': len(df['passenger_id'].unique())
        }
        return stats
    
    def get_area_density_stats(self):
        """获取区域密度统计数据"""
        if not self.area_density:
            return None
        
        densities = list(self.area_density.values())
        stats = {
            'average_density': np.mean(densities),
            'max_density': max(densities),
            'min_density': min(densities),
            'congested_areas': [area for area, density in self.area_density.items() if density > 0.8]
        }
        return stats
    
    def get_queue_stats(self):
        """获取队列统计数据"""
        if not self.queue_lengths:
            return None
        
        lengths = list(self.queue_lengths.values())
        stats = {
            'average_queue_length': np.mean(lengths),
            'max_queue_length': max(lengths),
            'min_queue_length': min(lengths)
        }
        return stats
    
    def clear(self):
        """清空统计数据"""
        self.data.fill(0)
        self.current_step = 0
        self.area_density.clear()
        self.queue_lengths.clear()
    
    def next_step(self):
        """进入下一步"""
        if self.current_step < self.max_steps - 1:
            self.current_step += 1