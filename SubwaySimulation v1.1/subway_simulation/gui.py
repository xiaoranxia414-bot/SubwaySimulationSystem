import tkinter as tk
from tkinter import ttk, filedialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import time
from core import StationGraph, SimulationEngine, PathPlanner, AnalyticsModule
from visualization import GraphVisualizer, HeatmapVisualizer, Dashboard

class SubwaySimulationGUI:
    """地铁站人流仿真系统GUI"""
    
    def __init__(self, root):
        """初始化GUI
        
        Args:
            root: Tkinter根窗口
        """
        self.root = root
        self.root.title("地铁站人流仿真系统")
        self.root.geometry("1200x800")
        
        # 创建仿真系统
        self.simulation = None
        self.is_running = False
        self.simulation_thread = None
        
        # 创建主框架
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建顶部控制栏
        self.control_frame = ttk.LabelFrame(self.main_frame, text="仿真控制")
        self.control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 仿真参数
        self.params_frame = ttk.LabelFrame(self.main_frame, text="仿真参数")
        self.params_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 可视化区域
        self.visualization_frame = ttk.LabelFrame(self.main_frame, text="可视化")
        self.visualization_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 分析报告区域
        self.report_frame = ttk.LabelFrame(self.main_frame, text="分析报告")
        self.report_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 初始化控件
        self._init_controls()
        self._init_params()
        self._init_visualization()
        self._init_report()
        
    def _init_controls(self):
        """初始化控制按钮"""
        # 按钮框架
        button_frame = ttk.Frame(self.control_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 开始按钮
        self.start_button = ttk.Button(button_frame, text="开始仿真", command=self.start_simulation)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # 暂停按钮
        self.pause_button = ttk.Button(button_frame, text="暂停仿真", command=self.pause_simulation, state=tk.DISABLED)
        self.pause_button.pack(side=tk.LEFT, padx=5)
        
        # 停止按钮
        self.stop_button = ttk.Button(button_frame, text="停止仿真", command=self.stop_simulation, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # 重置按钮
        self.reset_button = ttk.Button(button_frame, text="重置仿真", command=self.reset_simulation, state=tk.DISABLED)
        self.reset_button.pack(side=tk.LEFT, padx=5)
        
        # 加载配置按钮
        self.load_button = ttk.Button(button_frame, text="加载配置", command=self.load_config)
        self.load_button.pack(side=tk.RIGHT, padx=5)
        
        # 保存配置按钮
        self.save_button = ttk.Button(button_frame, text="保存配置", command=self.save_config)
        self.save_button.pack(side=tk.RIGHT, padx=5)
        
        # 状态标签
        self.status_var = tk.StringVar(value="就绪")
        self.status_label = ttk.Label(button_frame, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT, padx=10)
    
    def _init_params(self):
        """初始化仿真参数"""
        # 参数框架
        params_inner = ttk.Frame(self.params_frame)
        params_inner.pack(fill=tk.X, padx=5, pady=5)
        
        # 仿真步数
        ttk.Label(params_inner, text="仿真步数:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.steps_var = tk.IntVar(value=100)
        ttk.Entry(params_inner, textvariable=self.steps_var, width=10).grid(row=0, column=1, padx=5, pady=5)
        
        # 乘客生成速率（高峰期）
        ttk.Label(params_inner, text="高峰期乘客生成速率:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.peak_rate_var = tk.IntVar(value=10)
        ttk.Entry(params_inner, textvariable=self.peak_rate_var, width=10).grid(row=1, column=1, padx=5, pady=5)
        
        # 乘客生成速率（平峰期）
        ttk.Label(params_inner, text="平峰期乘客生成速率:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.normal_rate_var = tk.IntVar(value=5)
        ttk.Entry(params_inner, textvariable=self.normal_rate_var, width=10).grid(row=2, column=1, padx=5, pady=5)
        
        # 路径规划模式
        ttk.Label(params_inner, text="路径规划模式:").grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
        self.path_mode_var = tk.StringVar(value="shortest_time")
        path_modes = ["最短时间", "最短距离", "多目标优化"]
        path_mode_map = {"最短时间": "shortest_time", "最短距离": "shortest_distance", "多目标优化": "multi_objective"}
        self.path_mode_map = path_mode_map
        ttk.Combobox(params_inner, textvariable=self.path_mode_var, values=path_modes, width=15).grid(row=3, column=1, padx=5, pady=5)
    
    def _init_visualization(self):
        """初始化可视化区域"""
        # 可视化选项卡
        self.visualization_notebook = ttk.Notebook(self.visualization_frame)
        self.visualization_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 拓扑图选项卡
        self.graph_tab = ttk.Frame(self.visualization_notebook)
        self.visualization_notebook.add(self.graph_tab, text="拓扑图")
        
        # 热力图选项卡
        self.heatmap_tab = ttk.Frame(self.visualization_notebook)
        self.visualization_notebook.add(self.heatmap_tab, text="热力图")
        
        # 实时数据选项卡
        self.realtime_tab = ttk.Frame(self.visualization_notebook)
        self.visualization_notebook.add(self.realtime_tab, text="实时数据")
        
        # 初始化图形
        self._init_graph_visualization()
        self._init_heatmap_visualization()
        self._init_realtime_visualization()
    
    def _init_graph_visualization(self):
        """初始化拓扑图可视化"""
        # 创建画布
        self.graph_fig = plt.Figure(figsize=(8, 6), dpi=100)
        self.graph_canvas = FigureCanvasTkAgg(self.graph_fig, master=self.graph_tab)
        self.graph_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # 初始显示
        ax = self.graph_fig.add_subplot(111)
        ax.set_title("地铁站拓扑图")
        ax.text(0.5, 0.5, "请先开始仿真", ha='center', va='center')
        self.graph_canvas.draw()
    
    def _init_heatmap_visualization(self):
        """初始化热力图可视化"""
        # 创建画布
        self.heatmap_fig = plt.Figure(figsize=(8, 6), dpi=100)
        self.heatmap_canvas = FigureCanvasTkAgg(self.heatmap_fig, master=self.heatmap_tab)
        self.heatmap_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # 初始显示
        ax = self.heatmap_fig.add_subplot(111)
        ax.set_title("密度热力图")
        ax.text(0.5, 0.5, "请先开始仿真", ha='center', va='center')
        self.heatmap_canvas.draw()
    
    def _init_realtime_visualization(self):
        """初始化实时数据可视化"""
        # 创建画布
        self.realtime_fig = plt.Figure(figsize=(8, 6), dpi=100)
        self.realtime_canvas = FigureCanvasTkAgg(self.realtime_fig, master=self.realtime_tab)
        self.realtime_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # 初始显示
        ax = self.realtime_fig.add_subplot(111)
        ax.set_title("实时乘客数量")
        ax.set_xlabel("时间 (秒)")
        ax.set_ylabel("乘客数量")
        ax.text(0.5, 0.5, "请先开始仿真", ha='center', va='center')
        self.realtime_canvas.draw()
    
    def _init_report(self):
        """初始化分析报告区域"""
        # 报告文本框
        self.report_text = tk.Text(self.report_frame, wrap=tk.WORD)
        self.report_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.report_text.insert(tk.END, "分析报告将在此显示...")
        
        # 滚动条
        scrollbar = ttk.Scrollbar(self.report_frame, orient=tk.VERTICAL, command=self.report_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.report_text.config(yscrollcommand=scrollbar.set)
    
    def start_simulation(self):
        """开始仿真"""
        # 更新状态
        self.status_var.set("运行中")
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)
        self.reset_button.config(state=tk.NORMAL)
        self.is_running = True
        
        # 创建仿真系统
        self.simulation = SubwaySimulation()
        
        # 启动仿真线程
        self.simulation_thread = threading.Thread(target=self.run_simulation)
        self.simulation_thread.daemon = True
        self.simulation_thread.start()
    
    def pause_simulation(self):
        """暂停仿真"""
        self.status_var.set("暂停")
        self.is_running = False
        self.pause_button.config(text="继续仿真", command=self.resume_simulation)
    
    def resume_simulation(self):
        """继续仿真"""
        self.status_var.set("运行中")
        self.is_running = True
        self.pause_button.config(text="暂停仿真", command=self.pause_simulation)
        
        # 继续仿真线程
        self.simulation_thread = threading.Thread(target=self.run_simulation)
        self.simulation_thread.daemon = True
        self.simulation_thread.start()
    
    def stop_simulation(self):
        """停止仿真"""
        self.status_var.set("已停止")
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.reset_button.config(state=tk.NORMAL)
        
        # 生成分析报告
        self.generate_report()
    
    def reset_simulation(self):
        """重置仿真"""
        self.status_var.set("就绪")
        self.is_running = False
        self.simulation = None
        self.start_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.reset_button.config(state=tk.DISABLED)
        
        # 重置可视化
        self._reset_visualization()
        
        # 重置报告
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(tk.END, "分析报告将在此显示...")
    
    def run_simulation(self):
        """运行仿真"""
        steps = self.steps_var.get()
        
        for i in range(steps):
            if not self.is_running:
                break
            
            # 执行仿真步骤
            self.simulation.run_simulation_step()
            
            # 每10步更新一次可视化
            if (i + 1) % 10 == 0:
                self.update_visualization()
                self.status_var.set(f"运行中 - 步数: {i + 1}/{steps}")
            
            # 暂停一下，避免UI卡顿
            time.sleep(0.1)
        
        if self.is_running:
            self.stop_simulation()
    
    def update_visualization(self):
        """更新可视化"""
        if not self.simulation:
            return
        
        # 更新拓扑图
        self._update_graph_visualization()
        
        # 更新热力图
        self._update_heatmap_visualization()
        
        # 更新实时数据
        self._update_realtime_visualization()
    
    def _update_graph_visualization(self):
        """更新拓扑图"""
        if not self.simulation:
            return
        
        # 清空画布
        self.graph_fig.clear()
        
        # 绘制拓扑图
        ax = self.graph_fig.add_subplot(111)
        
        # 获取乘客列表
        passengers = self.simulation.simulation.get_passengers()
        
        # 绘制地铁站图
        graph = self.simulation.station_graph.get_graph()
        pos = {}
        for node, data in graph.nodes(data=True):
            pos[node] = (data['x'], data['y'])
        
        # 节点颜色
        node_colors = []
        for node, data in graph.nodes(data=True):
            node_type = data['type']
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
        
        # 绘制边和节点
        import networkx as nx
        nx.draw_networkx_edges(graph, pos, ax=ax)
        nx.draw_networkx_nodes(graph, pos, node_color=node_colors, ax=ax)
        nx.draw_networkx_labels(graph, pos, ax=ax)
        
        # 统计每个节点的乘客数量
        node_passenger_counts = {}
        for passenger in passengers:
            node_id = passenger.current_node
            if node_id not in node_passenger_counts:
                node_passenger_counts[node_id] = 0
            node_passenger_counts[node_id] += 1
        
        # 绘制乘客数量标签
        for node, count in node_passenger_counts.items():
            if node in pos:
                ax.text(pos[node][0], pos[node][1] + 0.1, f'{count}', 
                         ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        ax.set_title("地铁站拓扑图")
        ax.axis('off')
        self.graph_canvas.draw()
    
    def _update_heatmap_visualization(self):
        """更新热力图"""
        if not self.simulation:
            return
        
        # 清空画布
        self.heatmap_fig.clear()
        
        # 绘制热力图
        ax = self.heatmap_fig.add_subplot(111)
        
        # 获取密度数据
        densities = {}
        for node in self.simulation.station_graph.get_graph().nodes():
            node_info = self.simulation.station_graph.get_node(node)
            if node_info:
                densities[node] = node_info.get('current_density', 0)
        
        # 获取节点坐标
        node_coords = {}
        for node, data in self.simulation.station_graph.get_graph().nodes(data=True):
            node_coords[node] = (data['x'], data['y'])
        
        # 绘制热力图
        if node_coords:
            x_coords = [x for x, y in node_coords.values()]
            y_coords = [y for x, y in node_coords.values()]
            density_values = [densities.get(node, 0) for node in node_coords.keys()]
            
            # 绘制散点图，颜色表示密度
            scatter = ax.scatter(x_coords, y_coords, c=density_values, cmap='hot', s=100, alpha=0.7)
            
            # 添加颜色条
            self.heatmap_fig.colorbar(scatter, ax=ax, label='密度')
            
            # 添加节点标签
            for node, (x, y) in node_coords.items():
                ax.text(x, y, node, ha='center', va='center', fontsize=8, color='white')
        
        ax.set_title("密度热力图")
        self.heatmap_canvas.draw()
    
    def _update_realtime_visualization(self):
        """更新实时数据"""
        if not self.simulation:
            return
        
        # 清空画布
        self.realtime_fig.clear()
        
        # 绘制实时数据
        ax = self.realtime_fig.add_subplot(111)
        
        # 获取仿真数据
        current_time = self.simulation.simulation.get_current_time()
        passenger_count = len(self.simulation.simulation.get_passengers())
        
        # 绘制乘客数量趋势
        if not hasattr(self, 'time_data'):
            self.time_data = []
            self.passenger_data = []
        
        self.time_data.append(current_time)
        self.passenger_data.append(passenger_count)
        
        # 只显示最近50个数据点
        if len(self.time_data) > 50:
            self.time_data = self.time_data[-50:]
            self.passenger_data = self.passenger_data[-50:]
        
        ax.plot(self.time_data, self.passenger_data)
        ax.set_title("实时乘客数量")
        ax.set_xlabel("时间 (秒)")
        ax.set_ylabel("乘客数量")
        ax.grid(True)
        self.realtime_canvas.draw()
    
    def _reset_visualization(self):
        """重置可视化"""
        # 重置拓扑图
        self.graph_fig.clear()
        ax = self.graph_fig.add_subplot(111)
        ax.set_title("地铁站拓扑图")
        ax.text(0.5, 0.5, "请先开始仿真", ha='center', va='center')
        self.graph_canvas.draw()
        
        # 重置热力图
        self.heatmap_fig.clear()
        ax = self.heatmap_fig.add_subplot(111)
        ax.set_title("密度热力图")
        ax.text(0.5, 0.5, "请先开始仿真", ha='center', va='center')
        self.heatmap_canvas.draw()
        
        # 重置实时数据
        self.realtime_fig.clear()
        ax = self.realtime_fig.add_subplot(111)
        ax.set_title("实时乘客数量")
        ax.set_xlabel("时间 (秒)")
        ax.set_ylabel("乘客数量")
        ax.text(0.5, 0.5, "请先开始仿真", ha='center', va='center')
        self.realtime_canvas.draw()
        
        # 重置数据
        if hasattr(self, 'time_data'):
            delattr(self, 'time_data')
        if hasattr(self, 'passenger_data'):
            delattr(self, 'passenger_data')
    
    def generate_report(self):
        """生成分析报告"""
        if not self.simulation:
            return
        
        # 生成报告
        report = self.simulation.generate_analytics()
        
        # 显示报告
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(tk.END, "分析报告\n")
        self.report_text.insert(tk.END, "====================\n\n")
        
        if report['passenger_stats']:
            self.report_text.insert(tk.END, "乘客统计:\n")
            self.report_text.insert(tk.END, f"平均等待时间: {report['passenger_stats']['average_wait_time']:.2f}秒\n")
            self.report_text.insert(tk.END, f"最大等待时间: {report['passenger_stats']['max_wait_time']:.2f}秒\n")
            self.report_text.insert(tk.END, f"最小等待时间: {report['passenger_stats']['min_wait_time']:.2f}秒\n")
            self.report_text.insert(tk.END, f"乘客数量: {report['passenger_stats']['passenger_count']}\n")
            self.report_text.insert(tk.END, f"状态分布: {report['passenger_stats']['state_distribution']}\n\n")
        
        if report['density_stats']:
            self.report_text.insert(tk.END, "密度统计:\n")
            self.report_text.insert(tk.END, f"平均密度: {report['density_stats']['average_density']:.2f}\n")
            self.report_text.insert(tk.END, f"最大密度: {report['density_stats']['max_density']:.2f}\n")
            self.report_text.insert(tk.END, f"最小密度: {report['density_stats']['min_density']:.2f}\n")
            self.report_text.insert(tk.END, f"拥堵节点: {report['density_stats']['congested_nodes']}\n\n")
        
        if report['bottlenecks']:
            self.report_text.insert(tk.END, "瓶颈节点:\n")
            self.report_text.insert(tk.END, f"{report['bottlenecks']}\n")
    
    def load_config(self):
        """加载配置"""
        # 这里可以实现加载配置文件的功能
        pass
    
    def save_config(self):
        """保存配置"""
        # 这里可以实现保存配置文件的功能
        pass

class SubwaySimulation:
    """地铁站人流仿真系统"""
    
    def __init__(self):
        """初始化仿真系统"""
        # 创建地铁站图
        self.station_graph = self._create_station_graph()
        # 创建路径规划器
        self.path_planner = PathPlanner(self.station_graph)
        # 创建仿真引擎
        self.simulation = SimulationEngine(self.station_graph, self.path_planner)
        # 创建分析模块
        self.analytics = AnalyticsModule(self.station_graph)
    
    def _create_station_graph(self):
        """创建地铁站拓扑图"""
        graph = StationGraph()
        
        # 添加节点
        # 入口
        graph.add_node('entrance1', 'entrance', 50, 0, 5)
        graph.add_node('entrance2', 'entrance', 50, 0, 15)
        
        # 售票区
        graph.add_node('ticket1', 'ticket', 30, 5, 5)
        graph.add_node('ticket2', 'ticket', 30, 5, 15)
        
        # 安检区
        graph.add_node('security1', 'security', 20, 10, 5)
        graph.add_node('security2', 'security', 20, 10, 15)
        
        # 通道
        graph.add_node('corridor1', 'corridor', 100, 15, 10)
        
        # 楼梯/扶梯
        graph.add_node('stairs1', 'stairs', 10, 20, 5)
        graph.add_node('escalator1', 'escalator', 20, 20, 15)
        
        # 站台
        graph.add_node('platform1', 'platform', 200, 25, 5)
        graph.add_node('platform2', 'platform', 200, 25, 15)
        
        # 出口
        graph.add_node('exit1', 'exit', 50, 30, 5)
        graph.add_node('exit2', 'exit', 50, 30, 15)
        
        # 添加边
        # 入口到售票区
        graph.add_edge('entrance1', 'ticket1', 5, 2)
        graph.add_edge('entrance2', 'ticket2', 5, 2)
        
        # 售票区到安检区
        graph.add_edge('ticket1', 'security1', 5, 2)
        graph.add_edge('ticket2', 'security2', 5, 2)
        
        # 安检区到通道
        graph.add_edge('security1', 'corridor1', 5, 3)
        graph.add_edge('security2', 'corridor1', 5, 3)
        
        # 通道到楼梯/扶梯
        graph.add_edge('corridor1', 'stairs1', 5, 2)
        graph.add_edge('corridor1', 'escalator1', 5, 3)
        
        # 楼梯/扶梯到站台
        graph.add_edge('stairs1', 'platform1', 10, 2)
        graph.add_edge('escalator1', 'platform2', 10, 3)
        
        # 站台到出口
        graph.add_edge('platform1', 'exit1', 5, 2)
        graph.add_edge('platform2', 'exit2', 5, 2)
        
        return graph
    
    def run_simulation_step(self):
        """运行一个仿真步骤"""
        self.simulation.step()
    
    def generate_analytics(self):
        """生成分析报告"""
        # 收集数据
        passengers = self.simulation.get_passengers()
        densities = {}
        for node in self.station_graph.get_graph().nodes():
            node_info = self.station_graph.get_node(node)
            if node_info:
                densities[node] = node_info.get('current_density', 0)
        
        self.analytics.record_data(self.simulation.get_current_time(), passengers, densities)
        
        # 生成报告
        return self.analytics.generate_report()

if __name__ == "__main__":
    root = tk.Tk()
    app = SubwaySimulationGUI(root)
    root.mainloop()