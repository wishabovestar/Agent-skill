# -*- coding: utf-8 -*-
"""Hilbert 空间填充索引排序工具 (R162 落地)
用法: python hilbert_sort_index.py <n> [random_seed]
将 N 个 2D 数据点按 Hilbert 曲线序重排 — 局部性索引
输出: 局部性对比 (随机 vs Hilbert) + 缓存命中模拟
"""
import sys
import numpy as np


def hilbert_d2xy(d, n):
    """Hilbert 曲线: 1D 索引 d → 2D 坐标 (n×n 格)"""
    x = y = 0
    s = 1
    t = d
    while s < n:
        rx = 1 if (t // 2) & 1 else 0
        ry = 1 if (t ^ (1 if rx else 0)) & 1 else 0
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        t //= 4
        s *= 2
    return x, y


def hilbert_sort_2d(points):
    """按 Hilbert 序重排 2D 点 (返回索引顺序)"""
    # 归一化到 [0, n-1] 格
    x = points[:, 0]
    y = points[:, 1]
    xmin, xmax = x.min(), x.max()
    ymin, ymax = y.min(), y.max()
    n = 1
    while n * n < len(points):
        n *= 2
    xi = ((x - xmin) / (xmax - xmin) * (n - 1)).astype(int)
    yi = ((y - ymin) / (ymax - ymin) * (n - 1)).astype(int)
    # 反向映射: (x,y) → d
    pos = {}
    for d in range(n * n):
        pos[hilbert_d2xy(d, n)] = d
    order = sorted(range(len(points)), key=lambda i: pos[(xi[i], yi[i])])
    return order


def locality(perm, B):
    """邻域在存储中邻近比例 (4 邻域)"""
    pos = {p: i for i, p in enumerate(perm)}
    hits = 0
    tot = 0
    for i in range(len(perm)):
        x, y = i % 64, i // 64
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < 64 and 0 <= ny < 64:
                j = ny * 64 + nx
                if abs(pos[i] - pos[j]) <= B:
                    hits += 1
            tot += 1
    return hits / max(tot, 1)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4096
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 53
    rng = np.random.default_rng(seed)
    # 生成 n 个 2D 点 (聚簇数据 — 模拟真实嵌入)
    n_clusters = 8
    centers = rng.uniform(0, 100, (n_clusters, 2))
    assign = rng.integers(0, n_clusters, n)
    points = centers[assign] + rng.normal(0, 3, (n, 2))
    points = points[points[:, 0].argsort()]  # 原始顺序 (近似主题序)

    perm_random = rng.permutation(n)
    perm_hil = hilbert_sort_2d(points)
    print(f"[落地] Hilbert 排序工具 — {n} 点 (8 聚簇)")
    la = locality(perm_random, 64)
    lb = locality(perm_hil, 64)
    print(f"  局部性(64块): 随机 {la*100:.1f}% vs Hilbert {lb*100:.1f}% ({lb/la:.1f}x)")


if __name__ == "__main__":
    main()
