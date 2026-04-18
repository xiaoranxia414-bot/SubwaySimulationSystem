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
    
    def update_position(self, entity, old_x, old_y, new_x, new_y):
        """更新实体位置
        
        Args:
            entity: 实体
            old_x, old_y: 旧位置
            new_x, new_y: 新位置
        """
        old_key = self._get_cell_key(old_x, old_y)
        new_key = self._get_cell_key(new_x, new_y)
        if old_key != new_key:
            # 从旧单元格移除
            if old_key in self.grid:
                self.grid[old_key] = [(e, ex, ey) for e, ex, ey in self.grid[old_key] if e != entity]
            # 添加到新单元格
            if new_key not in self.grid:
                self.grid[new_key] = []
            self.grid[new_key].append((entity, new_x, new_y))
    
    def adaptive_cell_size(self, entity_count):
        """自适应调整单元格大小
        
        Args:
            entity_count: 实体数量
        """
        if entity_count < 100:
            self.cell_size = 2.0
        elif entity_count < 1000:
            self.cell_size = 1.5
        else:
            self.cell_size = 1.0