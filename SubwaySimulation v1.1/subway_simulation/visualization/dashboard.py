import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

class Dashboard:
    """实时仪表板"""
    
    def __init__(self, simulation):
        """初始化仪表板
        
        Args:
            simulation: 仿真引擎
        """
        self.simulation = simulation
        self.fig = None
        self.ax1 = None
        self.ax2 = None
        self.ax3 = None
        self.ax4 = None
        self.passenger_data = []
        self.density_data = []
        self.time_data = []
    
    def setup(self):
        """设置仪表板"""
        self.fig = plt.figure(figsize=(15, 10))
        
        # 乘客数量趋势图
        self.ax1 = self.fig.add_subplot(221)
        self.ax1.set_title('Passenger Count Over Time')
        self.ax1.set_xlabel('Time (seconds)')
        self.ax1.set_ylabel('Number of Passengers')
        self.ax1.grid(True)
        
        # 平均密度趋势图
        self.ax2 = self.fig.add_subplot(222)
        self.ax2.set_title('Average Density Over Time')
        self.ax2.set_xlabel('Time (seconds)')
        self.ax2.set_ylabel('Average Density')
        self.ax2.grid(True)
        
        # 乘客状态分布
        self.ax3 = self.fig.add_subplot(223)
        self.ax3.set_title('Passenger State Distribution')
        
        # 瓶颈节点
        self.ax4 = self.fig.add_subplot(224)
        self.ax4.set_title('Bottleneck Nodes')
        
        plt.tight_layout()
    
    def update(self, frame):
        """更新仪表板
        
        Args:
            frame: 帧编号
        """
        # 执行一个时间步
        if not self.simulation.step():
            return
        
        # 获取当前时间
        current_time = self.simulation.get_current_time()
        self.time_data.append(current_time)
        
        # 获取乘客数量
        passenger_count = len(self.simulation.get_passengers())
        self.passenger_data.append(passenger_count)
        
        # 获取平均密度
        stats = self.simulation.get_stats()
        if stats and 'area_density_stats' in stats and stats['area_density_stats']:
            avg_density = stats['area_density_stats'].get('average_density', 0)
            self.density_data.append(avg_density)
        else:
            self.density_data.append(0)
        
        # 更新乘客数量趋势图
        self.ax1.clear()
        self.ax1.set_title('Passenger Count Over Time')
        self.ax1.set_xlabel('Time (seconds)')
        self.ax1.set_ylabel('Number of Passengers')
        self.ax1.grid(True)
        self.ax1.plot(self.time_data, self.passenger_data)
        
        # 更新平均密度趋势图
        self.ax2.clear()
        self.ax2.set_title('Average Density Over Time')
        self.ax2.set_xlabel('Time (seconds)')
        self.ax2.set_ylabel('Average Density')
        self.ax2.grid(True)
        self.ax2.plot(self.time_data, self.density_data)
        
        # 更新乘客状态分布
        self.ax3.clear()
        self.ax3.set_title('Passenger State Distribution')
        
        if stats and 'passenger_stats' in stats and stats['passenger_stats']:
            state_dist = stats['passenger_stats'].get('state_distribution', {})
            if state_dist:
                states = list(state_dist.keys())
                counts = list(state_dist.values())
                self.ax3.bar(states, counts)
                self.ax3.set_xticklabels(states, rotation=45)
        
        # 更新瓶颈节点
        self.ax4.clear()
        self.ax4.set_title('Bottleneck Nodes')
        
        if stats and 'area_density_stats' in stats and stats['area_density_stats']:
            bottlenecks = stats['area_density_stats'].get('congested_areas', [])
            if bottlenecks:
                self.ax4.bar(range(len(bottlenecks)), [1]*len(bottlenecks))
                self.ax4.set_xticks(range(len(bottlenecks)))
                self.ax4.set_xticklabels(bottlenecks, rotation=45)
                self.ax4.set_ylim(0, 1.5)
        
        plt.tight_layout()
    
    def run(self, interval=1000):
        """运行仪表板
        
        Args:
            interval: 更新间隔（毫秒）
        """
        self.setup()
        ani = animation.FuncAnimation(self.fig, self.update, interval=interval)
        plt.show()
    
    def generate_summary(self, output_file='dashboard_summary.png'):
        """生成仪表板摘要
        
        Args:
            output_file: 输出文件路径
        """
        self.setup()
        
        # 执行多个时间步
        for _ in range(60):  # 运行60秒
            if not self.simulation.step():
                break
            
            # 获取当前时间
            current_time = self.simulation.get_current_time()
            self.time_data.append(current_time)
            
            # 获取乘客数量
            passenger_count = len(self.simulation.get_passengers())
            self.passenger_data.append(passenger_count)
            
            # 获取平均密度
            stats = self.simulation.get_stats()
            if stats and 'area_density_stats' in stats and stats['area_density_stats']:
                avg_density = stats['area_density_stats'].get('average_density', 0)
                self.density_data.append(avg_density)
            else:
                self.density_data.append(0)
        
        # 更新图表
        self.update(0)
        
        # 保存摘要
        plt.savefig(output_file)
        plt.close()