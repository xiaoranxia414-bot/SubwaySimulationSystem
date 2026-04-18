import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.colors import LinearSegmentedColormap

class HeatmapVisualizer:
    """热力图可视化"""
    
    def __init__(self, station_graph):
        """初始化热力图可视化
        
        Args:
            station_graph: 地铁站图
        """
        self.station_graph = station_graph
    
    def generate_heatmap(self, densities, output_file='heatmap.png'):
        """生成热力图
        
        Args:
            densities: 密度字典 {node_id: density}
            output_file: 输出文件路径
        """
        graph = self.station_graph.get_graph()
        
        # 获取所有节点的坐标
        node_coords = {}
        for node, data in graph.nodes(data=True):
            node_coords[node] = (data['x'], data['y'])
        
        # 创建网格
        # 计算边界
        x_coords = [data['x'] for node, data in graph.nodes(data=True)]
        y_coords = [data['y'] for node, data in graph.nodes(data=True)]
        
        if not x_coords or not y_coords:
            return
        
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)
        
        # 扩展边界
        padding = 1.0
        min_x -= padding
        max_x += padding
        min_y -= padding
        max_y += padding
        
        # 创建网格
        grid_size = 50
        x_grid = np.linspace(min_x, max_x, grid_size)
        y_grid = np.linspace(min_y, max_y, grid_size)
        X, Y = np.meshgrid(x_grid, y_grid)
        
        # 计算每个网格点的密度
        Z = np.zeros((grid_size, grid_size))
        
        for i, x in enumerate(x_grid):
            for j, y in enumerate(y_grid):
                # 计算到最近节点的距离
                min_dist = float('inf')
                closest_density = 0
                
                for node, (nx, ny) in node_coords.items():
                    dist = np.sqrt((x - nx)**2 + (y - ny)**2)
                    if dist < min_dist:
                        min_dist = dist
                        closest_density = densities.get(node, 0)
                
                # 根据距离加权密度
                weight = np.exp(-min_dist**2 / 0.5)  # 高斯权重
                Z[j, i] = closest_density * weight
        
        # 创建自定义颜色映射
        colors = ['white', 'lightyellow', 'yellow', 'orange', 'red', 'darkred']
        cmap = LinearSegmentedColormap.from_list('density', colors)
        
        # 绘图
        plt.figure(figsize=(15, 10))
        
        # 绘制热力图
        im = plt.imshow(Z, cmap=cmap, extent=[min_x, max_x, min_y, max_y], origin='lower')
        
        # 绘制节点
        for node, (x, y) in node_coords.items():
            density = densities.get(node, 0)
            # 根据密度设置节点大小
            size = 100 + density * 200
            plt.scatter(x, y, s=size, c='black', alpha=0.7)
            # 添加节点标签
            plt.text(x, y, node, ha='center', va='center', fontsize=8, color='white')
        
        # 添加颜色条
        cbar = plt.colorbar(im)
        cbar.set_label('Density')
        
        plt.title('Passenger Density Heatmap')
        plt.xlabel('X Coordinate')
        plt.ylabel('Y Coordinate')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_file)
        plt.close()
    
    def generate_time_series_heatmap(self, time_series_data, output_file='time_series_heatmap.png'):
        """生成时间序列热力图
        
        Args:
            time_series_data: 时间序列数据 {time: {node_id: density}}
            output_file: 输出文件路径
        """
        if not time_series_data:
            return
        
        # 获取所有节点
        graph = self.station_graph.get_graph()
        nodes = list(graph.nodes())
        
        # 按时间排序
        times = sorted(time_series_data.keys())
        
        # 创建数据矩阵
        data = []
        for time in times:
            time_data = time_series_data[time]
            row = [time_data.get(node, 0) for node in nodes]
            data.append(row)
        
        data = np.array(data)
        
        # 创建自定义颜色映射
        colors = ['white', 'lightyellow', 'yellow', 'orange', 'red', 'darkred']
        cmap = LinearSegmentedColormap.from_list('density', colors)
        
        # 绘图
        plt.figure(figsize=(15, 10))
        
        # 绘制热力图
        im = plt.imshow(data, cmap=cmap, aspect='auto')
        
        # 设置标签
        plt.xticks(np.arange(len(nodes)), nodes, rotation=90)
        plt.yticks(np.arange(len(times)), times)
        
        # 添加颜色条
        cbar = plt.colorbar(im)
        cbar.set_label('Density')
        
        plt.title('Time Series Density Heatmap')
        plt.xlabel('Node')
        plt.ylabel('Time (seconds)')
        plt.tight_layout()
        plt.savefig(output_file)
        plt.close()