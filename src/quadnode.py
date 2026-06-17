import numpy as np
import random

class QuadNode:
    """Quadtree node storing spatial bbox, point indices, level, and children."""
    def __init__(self, bbox, indices_src, indices_tgt, indices_tgt_neigh, center, level, parent=None, is_anthropic=False):
        self.bbox = bbox
        self.id = int(np.sum(np.array(self.bbox['min_bound']) * np.array([10**3, 10**6, 10**9])) + level)
        self.center = center
        self.indices_src = indices_src
        self.indices_tgt = indices_tgt
        self.indices_tgt_neigh = indices_tgt_neigh
        self.level = level
        self.fitness = -1
        self.inlier_rmse = -1
        self.planarity = -1
        self.global_transform = np.zeros((4, 4))
        self.local_transform = np.zeros((4, 4))
        self.metrics = {}
        self.size = np.min([len(indices_src), len(indices_tgt)])
        self.parent = parent
        self.children = []
        self.anthropic_state = 0 if is_anthropic else -1   # 0 = normal, 1 = new building, 2 = destruction
        self.is_leaf = True
        self.is_absurd = False
        # self.test = random.random()

    def __len__(self):
        counter = len(self.children)
        for child in self.children:
            if child != None:
                counter += len(child)
        return counter
    
    def get_root(self):
        if self.parent == None:
            return self
        parent = self.parent
        while parent.parent != None:
            parent = parent.parent
        return parent


if __name__ == "__main__":
    print(random.random())