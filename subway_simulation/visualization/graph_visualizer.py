import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

class GraphVisualizer:
    """图结构可视化"""
    
    def __init__(self, station_graph):
        """初始化图结构可视化
        
        Args:
            station_graph: 地铁站图
        """
        self.station_graph = station_graph
    
    def visualize(self, output_file='station_graph.png'):
        """可视化地铁站图
        
        Args:
            output_file: 输出文件路径
        """
        graph = self.station_graph.get_graph()
        
        # 节点位置
        pos = {}
        for node, data in graph.nodes(data=True):
            pos[node] = (data['x'], data['y'])
        
        # 节点颜色映射
        node_colors = []
        for node, data in graph.nodes(data=True):
            node_type = data['type']
            # 根据节点类型设置颜色
            if node_type == 'entrance':
                node_colors.append('green')
            elif node_type == 'exit':
                node_colors.append('red')
            elif node_type == 'security':
                node_colors.append('yellow')
            elif node_type == 'ticket':
                node_colors.append('blue')
            elif node_type == 'platform':
                node_colors.append('purple')
            elif node_type == 'corridor':
                node_colors.append('gray')
            else:
                node_colors.append('white')
        
        # 节点大小（基于容量）
        node_sizes = []
        for node, data in graph.nodes(data=True):
            node_sizes.append(data['capacity'] * 10)
        
        # 边颜色（基于拥堵系数）
        edge_colors = []
        for u, v, data in graph.edges(data=True):
            congestion = data['congestion_factor']
            # 根据拥堵系数设置颜色
            if congestion < 1.2:
                edge_colors.append('green')
            elif congestion < 1.5:
                edge_colors.append('yellow')
            else:
                edge_colors.append('red')
        
        # 绘图
        plt.figure(figsize=(15, 10))
        
        # 绘制边
        nx.draw_networkx_edges(graph, pos, edge_color=edge_colors, width=2)
        
        # 绘制节点
        nx.draw_networkx_nodes(graph, pos, node_color=node_colors, node_size=node_sizes)
        
        # 绘制节点标签
        nx.draw_networkx_labels(graph, pos, font_size=10)
        
        # 添加图例
        legend_elements = [
            plt.Line2D([0], [0], marker='o', color='w', label='Entrance', markerfacecolor='green', markersize=10),
            plt.Line2D([0], [0], marker='o', color='w', label='Exit', markerfacecolor='red', markersize=10),
            plt.Line2D([0], [0], marker='o', color='w', label='Security', markerfacecolor='yellow', markersize=10),
            plt.Line2D([0], [0], marker='o', color='w', label='Ticket', markerfacecolor='blue', markersize=10),
            plt.Line2D([0], [0], marker='o', color='w', label='Platform', markerfacecolor='purple', markersize=10),
            plt.Line2D([0], [0], marker='o', color='w', label='Corridor', markerfacecolor='gray', markersize=10),
            plt.Line2D([0], [0], color='green', label='Low Congestion', linewidth=2),
            plt.Line2D([0], [0], color='yellow', label='Medium Congestion', linewidth=2),
            plt.Line2D([0], [0], color='red', label='High Congestion', linewidth=2)
        ]
        plt.legend(handles=legend_elements, loc='upper right')
        
        plt.title('Subway Station Topology')
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_file)
        plt.close()
    
    def visualize_with_passengers(self, passengers, output_file='station_with_passengers.png'):
        """可视化地铁站图和乘客位置
        
        Args:
            passengers: 乘客列表
            output_file: 输出文件路径
        """
        graph = self.station_graph.get_graph()
        
        # 节点位置
        pos = {}
        for node, data in graph.nodes(data=True):
            pos[node] = (data['x'], data['y'])
        
        # 节点颜色映射
        node_colors = []
        for node, data in graph.nodes(data=True):
            node_type = data['type']
            # 根据节点类型设置颜色
            if node_type == 'entrance':
                node_colors.append('green')
            elif node_type == 'exit':
                node_colors.append('red')
            elif node_type == 'security':
                node_colors.append('yellow')
            elif node_type == 'ticket':
                node_colors.append('blue')
            elif node_type == 'platform':
                node_colors.append('purple')
            elif node_type == 'corridor':
                node_colors.append('gray')
            else:
                node_colors.append('white')
        
        # 节点大小（基于容量）
        node_sizes = []
        for node, data in graph.nodes(data=True):
            node_sizes.append(data['capacity'] * 10)
        
        # 统计每个节点的乘客数量
        node_passenger_counts = {}
        for passenger in passengers:
            node_id = passenger.current_node
            if node_id not in node_passenger_counts:
                node_passenger_counts[node_id] = 0
            node_passenger_counts[node_id] += 1
        
        # 绘图
        plt.figure(figsize=(15, 10))
        
        # 绘制边
        nx.draw_networkx_edges(graph, pos, edge_color='gray', width=1)
        
        # 绘制节点
        nx.draw_networkx_nodes(graph, pos, node_color=node_colors, node_size=node_sizes)
        
        # 绘制乘客数量标签
        for node, count in node_passenger_counts.items():
            if node in pos:
                plt.text(pos[node][0], pos[node][1] + 0.1, f'{count}', 
                         ha='center', va='bottom', fontsize=12, fontweight='bold')
        
        # 绘制节点标签
        nx.draw_networkx_labels(graph, pos, font_size=10)
        
        plt.title('Subway Station with Passengers')
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_file)
        plt.close()