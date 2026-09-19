"""Uniform-grid broad phase for cheap collision candidate queries."""
from collections import defaultdict
class SpatialHash:
    def __init__(self, cell_size=32): self.cell_size=cell_size; self.cells=defaultdict(list)
    def clear(self): self.cells.clear()
    def _cell(self,x,y): return int(x//self.cell_size), int(y//self.cell_size)
    def insert(self, item): self.cells[self._cell(item.pos.x,item.pos.y)].append(item)
    def query(self,x,y,radius=0):
        c=self.cell_size; out=[]
        for cy in range(int((y-radius)//c), int((y+radius)//c)+1):
            for cx in range(int((x-radius)//c), int((x+radius)//c)+1): out.extend(self.cells.get((cx,cy), ()))
        return out
