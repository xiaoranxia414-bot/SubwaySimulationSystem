from core import StationGraph, SimulationEngine, PathPlanner, AnalyticsModule
from visualization import GraphVisualizer, HeatmapVisualizer, Dashboard

class SubwaySimulation:
    """地铁站人群流动仿真系统"""
    
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
        # 创建可视化工具
        self.graph_visualizer = GraphVisualizer(self.station_graph)
        self.heatmap_visualizer = HeatmapVisualizer(self.station_graph)
    
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
    
    def run_simulation(self, steps=100):
        """运行仿真
        
        Args:
            steps: 运行步数
        """
        print("开始运行仿真...")
        
        for i in range(steps):
            if not self.simulation.step():
                break
            
            if (i + 1) % 10 == 0:
                print(f"运行步数: {i + 1}/{steps}")
        
        print("仿真结束!")
    
    def generate_visualizations(self):
        """生成可视化结果"""
        print("生成可视化结果...")
        
        # 可视化地铁站图
        self.graph_visualizer.visualize()
        print("生成地铁站拓扑图: station_graph.png")
        
        # 可视化乘客分布
        passengers = self.simulation.get_passengers()
        self.graph_visualizer.visualize_with_passengers(passengers)
        print("生成乘客分布图: station_with_passengers.png")
        
        # 生成热力图
        stats = self.simulation.get_stats()
        if stats and 'area_density_stats' in stats:
            densities = {}
            for node in self.station_graph.get_graph().nodes():
                node_info = self.station_graph.get_node(node)
                if node_info:
                    densities[node] = node_info.get('current_density', 0)
            
            self.heatmap_visualizer.generate_heatmap(densities)
            print("生成密度热力图: heatmap.png")
    
    def generate_analytics(self):
        """生成分析报告"""
        print("生成分析报告...")
        
        # 收集数据
        passengers = self.simulation.get_passengers()
        densities = {}
        for node in self.station_graph.get_graph().nodes():
            node_info = self.station_graph.get_node(node)
            if node_info:
                densities[node] = node_info.get('current_density', 0)
        
        self.analytics.record_data(self.simulation.get_current_time(), passengers, densities)
        
        # 生成报告
        report = self.analytics.generate_report()
        
        # 打印报告
        print("\n分析报告:")
        print("====================")
        
        if report['passenger_stats']:
            print("乘客统计:")
            print(f"平均等待时间: {report['passenger_stats']['average_wait_time']:.2f}秒")
            print(f"最大等待时间: {report['passenger_stats']['max_wait_time']:.2f}秒")
            print(f"最小等待时间: {report['passenger_stats']['min_wait_time']:.2f}秒")
            print(f"乘客数量: {report['passenger_stats']['passenger_count']}")
            print(f"状态分布: {report['passenger_stats']['state_distribution']}")
        
        if report['density_stats']:
            print("\n密度统计:")
            print(f"平均密度: {report['density_stats']['average_density']:.2f}")
            print(f"最大密度: {report['density_stats']['max_density']:.2f}")
            print(f"最小密度: {report['density_stats']['min_density']:.2f}")
            print(f"拥堵节点: {report['density_stats']['congested_nodes']}")
        
        if report['bottlenecks']:
            print("\n瓶颈节点:")
            print(report['bottlenecks'])
    
    def run_dashboard(self):
        """运行实时仪表板"""
        print("运行实时仪表板...")
        dashboard = Dashboard(self.simulation)
        dashboard.run()

if __name__ == "__main__":
    # 创建仿真系统
    simulation = SubwaySimulation()
    
    # 运行仿真
    simulation.run_simulation(steps=100)
    
    # 生成可视化结果
    simulation.generate_visualizations()
    
    # 生成分析报告
    simulation.generate_analytics()
    
    # 运行实时仪表板（可选）
    # simulation.run_dashboard()