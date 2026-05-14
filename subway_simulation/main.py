from core import StationGraph, SimulationEngine, PathPlanner, AnalyticsModule
from visualization import GraphVisualizer, HeatmapVisualizer, Dashboard


class SubwaySimulation:
    """地铁站人群流动仿真系统 — 命令行版本"""

    def __init__(self, station_size="中型站", custom_graph=None,
                 total_steps=3600, period_rules=None, start_hour=6):
        self.station_size = station_size
        self.station_graph = custom_graph if custom_graph else self._create_station_graph()
        self.path_planner = PathPlanner(self.station_graph)
        self.simulation = SimulationEngine(
            self.station_graph, self.path_planner,
            period_rules=period_rules, start_hour=start_hour
        )
        self.analytics = AnalyticsModule(self.station_graph)
        self.graph_visualizer = GraphVisualizer(self.station_graph)
        self.heatmap_visualizer = HeatmapVisualizer(self.station_graph)

    def _create_station_graph(self):
        """创建地铁站拓扑图（支持小型/中型/大型/换乘站，多楼层）"""
        graph = StationGraph()
        cfg = {
            "小型站": dict(ec=30, tc=20, sc=15, gc=10, cc=80,  pc=150, xc=30, n=1),
            "中型站": dict(ec=50, tc=30, sc=20, gc=15, cc=100, pc=200, xc=50, n=2),
            "大型站": dict(ec=80, tc=50, sc=30, gc=25, cc=150, pc=300, xc=80, n=3),
            "换乘站": dict(ec=100, tc=60, sc=40, gc=30, cc=200, pc=400, xc=100, n=4),
        }
        c = cfg.get(self.station_size, cfg["中型站"])
        n = c['n']

        # 多楼层设计：
        # floor=0  : 地面层（入口、出口）
        # floor=1  : 站厅层（售票、安检、闸机、通道）
        # floor=-1 : 站台层（楼梯/扶梯、站台）
        for i in range(1, n + 1):
            y_offset = (i - 1) * 80
            # 地面层
            graph.add_node(f'entrance{i}',  'entrance',  c['ec'], 0,  10 + y_offset,
                           floor=0, area=120.0, base_speed=1.2)
            graph.add_node(f'exit{i}',      'exit',      c['xc'], 600, 10 + y_offset,
                           floor=0, area=100.0, base_speed=1.2)
            # 站厅层
            graph.add_node(f'ticket{i}',    'ticket',    c['tc'], 80, 10 + y_offset,
                           floor=1, area=80.0, base_speed=0.8, service_rate=0.4)
            graph.add_node(f'security{i}',  'security',  c['sc'], 160, 10 + y_offset,
                           floor=1, area=60.0, base_speed=0.6, service_rate=0.25)
            graph.add_node(f'gate{i}',      'gate',      c['gc'], 240, 10 + y_offset,
                           floor=1, area=40.0, base_speed=1.0, service_rate=0.6)
            # 站台层（地下）
            graph.add_node(f'stairs{i}',    'stairs',    10,      400, 10 + y_offset,
                           floor=-1, area=30.0, base_speed=0.5)
            graph.add_node(f'escalator{i}', 'escalator', 20,      400, 30 + y_offset,
                           floor=-1, area=50.0, base_speed=0.8)
            graph.add_node(f'platform{i}',  'platform',  c['pc'], 500, 20 + y_offset,
                           floor=-1, area=400.0, base_speed=1.0, dwell_time=30)

        # 通道在站厅层
        graph.add_node('corridor1', 'corridor', c['cc'], 320, 40 + (n-1)*40,
                       floor=1, area=300.0, base_speed=1.2)

        for i in range(1, n + 1):
            # 地面 → 站厅
            graph.add_edge(f'entrance{i}',  f'ticket{i}',    20, 3, capacity=15, base_time=2.0)
            # 站厅内部流程
            graph.add_edge(f'ticket{i}',    f'security{i}',  20, 3, capacity=10, base_time=2.0)
            graph.add_edge(f'security{i}',  f'gate{i}',      15, 3, capacity=8,  base_time=1.5)
            graph.add_edge(f'gate{i}',      'corridor1',     25, 4, capacity=20, base_time=3.0)
            # 站厅 → 站台（楼梯/扶梯）
            graph.add_edge('corridor1',     f'stairs{i}',    30, 3, capacity=8,  base_time=4.0)
            graph.add_edge('corridor1',     f'escalator{i}', 30, 4, capacity=12, base_time=3.0)
            # 站台内部
            graph.add_edge(f'stairs{i}',    f'platform{i}',  40, 2, capacity=6,  base_time=8.0)
            graph.add_edge(f'escalator{i}', f'platform{i}',  40, 3, capacity=10, base_time=5.0)
            # 站台 → 地面（出口）
            graph.add_edge(f'platform{i}',  f'exit{i}',      30, 3, capacity=15, base_time=3.0)

        return graph

    def run_simulation(self, steps=3600, verbose=True):
        """运行仿真"""
        if verbose:
            print(f"开始运行仿真... 站点规模: {self.station_size}, 步数: {steps}")

        for i in range(steps):
            self.simulation.step()

            if verbose and (i + 1) % 300 == 0:
                pcount = len(self.simulation.get_passengers())
                finished = len(self.simulation.finished_wait_times)
                print(f"  步数: {i+1}/{steps} | 站内乘客: {pcount} | 已完成: {finished}")

        if verbose:
            print("仿真结束!")
            finished = self.simulation.get_finished_stats()
            if finished:
                print(f"  已完成乘客: {finished['finished_count']}")
                print(f"  平均等待时间: {finished['avg_wait_time']:.1f}秒")
                print(f"  平均通行时间: {finished['avg_travel_time']:.1f}秒")

    def generate_visualizations(self):
        """生成可视化结果"""
        print("生成可视化结果...")

        self.graph_visualizer.visualize()
        print("  生成地铁站拓扑图: station_graph.png")

        passengers = self.simulation.get_passengers()
        self.graph_visualizer.visualize_with_passengers(passengers)
        print("  生成乘客分布图: station_with_passengers.png")

        densities = {
            node: (self.station_graph.get_node(node) or {}).get('current_density', 0)
            for node in self.station_graph.get_graph().nodes()
        }
        self.heatmap_visualizer.generate_heatmap(densities)
        print("  生成密度热力图: heatmap.png")

    def generate_analytics(self):
        """生成分析报告"""
        print("\n生成分析报告...")

        passengers = self.simulation.get_passengers()
        densities = {
            node: (self.station_graph.get_node(node) or {}).get('current_density', 0)
            for node in self.station_graph.get_graph().nodes()
        }
        self.analytics.record_data(self.simulation.get_current_time(), passengers, densities)

        report = self.analytics.generate_report()

        print("\n" + "=" * 50)
        print("分析报告")
        print("=" * 50)

        if report['passenger_stats']:
            ps = report['passenger_stats']
            print(f"\n【乘客统计】")
            print(f"  乘客数量: {ps['passenger_count']}")
            print(f"  平均等待时间: {ps['average_wait_time']:.2f}秒")
            print(f"  最大等待时间: {ps['max_wait_time']:.2f}秒")
            print(f"  状态分布: {ps['state_distribution']}")

        if report['density_stats']:
            ds = report['density_stats']
            print(f"\n【密度统计】")
            print(f"  平均密度: {ds['average_density']:.4f} 人/m²")
            print(f"  最大密度: {ds['max_density']:.4f} 人/m²")
            print(f"  拥堵节点: {ds['congested_nodes']}")

        bottlenecks = report['bottlenecks']
        if bottlenecks:
            print(f"\n【瓶颈节点 Top{len(bottlenecks)}】")
            for b in bottlenecks[:5]:
                print(f"  {b['node_id']}: 平均密度={b['avg_density']}, "
                      f"高密度占比={b['high_density_ratio']*100:.1f}%")

        finished = self.simulation.get_finished_stats()
        if finished:
            print(f"\n【已完成乘客】")
            print(f"  总人数: {finished['finished_count']}")
            print(f"  平均等待: {finished['avg_wait_time']:.1f}秒")
            print(f"  平均通行: {finished['avg_travel_time']:.1f}秒")

        # 生成可视化图表
        self.analytics.plot_passenger_flow()
        self.analytics.plot_state_distribution()
        self.analytics.plot_heatmap()
        self.analytics.plot_bottleneck_analysis()
        print("\n  已保存: passenger_flow.png, state_distribution.png, "
              "heatmap.png, bottleneck_analysis.png")

        return report

    def run_dashboard(self):
        """运行实时仪表板"""
        print("运行实时仪表板...")
        dashboard = Dashboard(self.simulation)
        dashboard.run()


if __name__ == "__main__":
    import sys

    # 解析命令行参数
    station_size = "中型站"
    steps = 3600
    if len(sys.argv) > 1:
        station_size = sys.argv[1]
    if len(sys.argv) > 2:
        steps = int(sys.argv[2])

    # 创建仿真系统
    simulation = SubwaySimulation(station_size=station_size, total_steps=steps)

    # 运行仿真
    simulation.run_simulation(steps=steps)

    # 生成可视化结果
    simulation.generate_visualizations()

    # 生成分析报告
    simulation.generate_analytics()
