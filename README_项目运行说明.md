# 地铁站人群流动仿真系统 — 项目运行说明

## 一、环境要求

- Python 3.10+
- 依赖包：networkx, numpy, matplotlib, pandas, seaborn, PyQt5

## 二、快速安装依赖

```bash
pip install networkx numpy matplotlib pandas seaborn PyQt5
```

## 三、运行方式

### 1. 命令行版本（推荐用于快速测试和批量仿真）

```bash
cd subway_simulation
python main.py [站点规模] [仿真步数]
```

示例：
```bash
python main.py 中型站 1200    # 中型站，仿真1200步（20分钟）
python main.py 大型站 1800    # 大型站，仿真1800步（30分钟）
python main.py 换乘站 3600    # 换乘站，仿真3600步（60分钟）
```

支持的站点规模：`小型站`、`中型站`、`大型站`、`换乘站`

各规模站点均采用**多楼层拓扑结构**：
- **地面层（floor=0）**：入口（entrance）、出口（exit）
- **站厅层（floor=1）**：售票（ticket）、安检（security）、闸机（gate）、通道（corridor）
- **站台层（floor=-1）**：楼梯（stairs）、扶梯（escalator）、站台（platform）

### 2. GUI 版本（推荐用于交互式演示）

```bash
cd subway_simulation
python gui_qt.py
```

GUI 功能：
- 左侧控制面板设置仿真参数（时长、起始时间、路径模式、站点规模、时段流量）
- 拓扑图标签页：可拖拽编辑节点和边，实时显示拥堵颜色，**支持多楼层可视化**
  - 节点显示楼层标签（B1/F0/F1 等）
  - 不同楼层边框样式区分（地下层蓝色虚线、地面层黑色实线、站厅层橙色实线）
  - 双击节点可编辑楼层属性（-5~10）
- 热力图标签页：显示各区域密度分布
- 实时数据标签页：动态折线图（乘客数/密度/队列长度）
- 分析报告标签页：仿真结束后自动生成统计报告

## 四、输出文件

运行后会生成以下可视化文件：
- `station_graph.png` — 地铁站拓扑图
- `station_with_passengers.png` — 带乘客分布的拓扑图
- `heatmap.png` — 客流热力图
- `passenger_flow.png` — 乘客流量时间序列
- `state_distribution.png` — 乘客状态分布图
- `bottleneck_analysis.png` — 瓶颈节点分析图

## 五、项目结构

```
subway_simulation/
├── core/                       # 核心模块
│   ├── station_graph.py        # 地铁站拓扑图（你负责）
│   ├── passenger.py            # 乘客状态机（你负责）
│   ├── path_planner.py         # 路径规划器（你负责）
│   ├── simulation_engine.py    # 仿真引擎（同学A负责）
│   ├── analytics.py            # 数据分析模块（同学A负责）
│   └── simulation_config.py    # 仿真配置
├── utils/                      # 工具模块
│   ├── priority_queue.py       # 优先队列（你负责）
│   ├── spatial_hash.py         # 空间哈希（你负责）
│   └── stats_collector.py      # 统计收集器（同学A负责）
├── visualization/              # 可视化模块（同学B负责）
│   ├── graph_visualizer.py
│   ├── heatmap.py
│   └── dashboard.py
├── gui.py                      # Tkinter旧版GUI（已废弃）
├── gui_qt.py                   # PyQt5主界面（同学B负责）
├── main.py                     # 命令行入口
└── requirements.txt            # 依赖列表
```

## 六、核心功能验证

### 路径规划测试
```python
from core import StationGraph, PathPlanner
from main import SubwaySimulation

sim = SubwaySimulation(station_size='中型站')
pp = sim.path_planner

# 测试5种路径模式
for mode in ['shortest_time', 'shortest_distance', 'min_switches', 'multi_objective']:
    path = pp.find_path('entrance1', 'exit1', mode)
    print(f"{mode}: {path}")
    print(f"  评估: {pp.evaluate_path(path)}")
```

### 仿真压力测试
```python
sim = SubwaySimulation(station_size='中型站', total_steps=1200)
for i in range(1200):
    sim.simulation.step()

finished = sim.simulation.get_finished_stats()
print(f"完成乘客: {finished['finished_count']}")
print(f"平均等待: {finished['avg_wait_time']:.1f}秒")
print(f"平均通行: {finished['avg_travel_time']:.1f}秒")
```

## 七、常见问题

**Q: 运行 gui_qt.py 报错 `No module named 'PyQt5'`**
A: 安装 PyQt5：`pip install PyQt5`

**Q: 仿真过程中乘客堆积在入口不移动**
A: 已修复。原因为节点容量限制过严，现改为基于面积×密度的动态限制。

**Q: 无票乘客是否必须排队购票？**
A: 不一定。系统模拟了真实场景：无票乘客根据熟悉度有 40%~80% 概率直接跳过售票区（使用移动支付/交通卡直接在闸机扫码），更符合现代地铁的实际通行方式。

**Q: NetworkX 3.x 下 `nx.write_gpickle` 报错**
A: 已修复。改用 Python 标准库 `pickle` 直接序列化。

## 八、小组分工

| 成员 | 负责内容 | 核心文件 |
|------|---------|---------|
| 同学A（组长） | 系统架构、后端开发、仿真引擎、列车系统、数据分析 | `simulation_engine.py`, `analytics.py`, `stats_collector.py` |
| **你** | **算法设计、数据结构选取、算法改进** | **`path_planner.py`, `station_graph.py`, `passenger.py`, `spatial_hash.py`, `priority_queue.py`** |
| 同学B | 前端界面、可视化模块、部分算法协作 | `gui_qt.py`, `visualization/` |
