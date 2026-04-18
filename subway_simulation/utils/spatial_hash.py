class SpatialHash:
    """空间哈希实现，用于高效碰撞检测"""
    
    def __init__(self, cell_size=1.0):
        """初始化空间哈希
        
        Args:
            cell_size: 单元格大小
        """
        self.cell_size = cell_size
        self.grid = {}
    
    def _get_cell_key(self, x, y):
        """获取单元格键"""
        return (int(x // self.cell_size), int(y // self.cell_size))
    
    def insert(self, entity, x, y):
        """插入实体到空间哈希"""
        key = self._get_cell_key(x, y)
        if key not in self.grid:
            self.grid[key] = []
        self.grid[key].append((entity, x, y))
    
    def get_neighbors(self, x, y, radius):
        """获取指定位置附近的实体"""
        neighbors = []
        min_cell = (int((x - radius) // self.cell_size), int((y - radius) // self.cell_size))
        max_cell = (int((x + radius) // self.cell_size), int((y + radius) // self.cell_size))
        
        for i in range(min_cell[0], max_cell[0] + 1):
            for j in range(min_cell[1], max_cell[1] + 1):
                key = (i, j)
                if key in self.grid:
                    for entity, ex, ey in self.grid[key]:
                        distance = ((ex - x) ** 2 + (ey - y) ** 2) ** 0.5
                        if distance <= radius:
                            neighbors.append((entity, ex, ey))
        
        return neighbors
    
    def clear(self):
        """清空空间哈希"""
        self.grid.clear()
    
    def remove(self, entity, x, y):
        """从空间哈希中移除实体"""
        key = self._get_cell_key(x, y)
        if key in self.grid:
            self.grid[key] = [(e, ex, ey) for e, ex, ey in self.grid[key] if e != entity]