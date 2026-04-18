import heapq

class PriorityQueue:
    """优先队列实现，用于路径规划算法"""
    
    def __init__(self):
        self._queue = []
        self._index = 0
    
    def push(self, item, priority):
        """将项目推入队列"""
        heapq.heappush(self._queue, (priority, self._index, item))
        self._index += 1
    
    def pop(self):
        """弹出优先级最高的项目"""
        if self._queue:
            return heapq.heappop(self._queue)[-1]
        raise IndexError("优先队列为空")
    
    def is_empty(self):
        """检查队列是否为空"""
        return len(self._queue) == 0
    
    def size(self):
        """返回队列大小"""
        return len(self._queue)