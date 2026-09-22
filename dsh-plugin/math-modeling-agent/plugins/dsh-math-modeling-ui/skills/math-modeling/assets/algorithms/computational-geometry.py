"""Planar Euclidean examples; coordinates must already share projected units."""
import json

import numpy as np
from scipy.spatial import ConvexHull, Delaunay, KDTree, Voronoi


def rigid_transform(points, angle, translation):
    points = np.asarray(points, dtype=float)
    translation = np.asarray(translation, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or translation.shape != (2,):
        raise ValueError("Expected planar points and a 2-vector translation")
    if not (np.isfinite(points).all() and np.isfinite(translation).all() and np.isfinite(angle)):
        raise ValueError("Coordinates and angle must be finite")
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    return points @ rotation.T + translation


def segment_intersection(a, b, c, d, *, atol=1e-12):
    """Return one intersection or None; overlapping collinear segments are ambiguous.

    atol is an absolute cross-product tolerance in squared coordinate units.
    This teaching routine is not an exact-predicate computational geometry kernel.
    """
    vertices = np.asarray([a, b, c, d], dtype=float)
    if vertices.shape != (4, 2) or not np.isfinite(vertices).all() or not np.isfinite(atol) or atol <= 0:
        raise ValueError("Expected four finite planar points and positive atol")
    a, b, c, d = vertices
    r, s = b - a, d - c
    if np.dot(r, r) <= atol or np.dot(s, s) <= atol:
        raise ValueError("Degenerate segments need a point-distance contract")

    def cross(u, v):
        return u[0] * v[1] - u[1] * v[0]

    denominator = cross(r, s)
    if abs(denominator) <= atol:
        if abs(cross(c - a, r)) > atol:
            return None
        endpoints = sorted([np.dot(c - a, r) / np.dot(r, r), np.dot(d - a, r) / np.dot(r, r)])
        low, high = max(0.0, endpoints[0]), min(1.0, endpoints[1])
        parameter_tolerance = atol / np.dot(r, r)
        if low > high + parameter_tolerance:
            return None
        if high - low <= parameter_tolerance:
            return a + np.clip((low + high) / 2, 0, 1) * r
        raise ValueError("Collinear overlap has no unique intersection point")
    t, u = cross(c - a, s) / denominator, cross(c - a, r) / denominator
    parameter_tolerance = atol / abs(denominator)
    if -parameter_tolerance <= t <= 1 + parameter_tolerance and -parameter_tolerance <= u <= 1 + parameter_tolerance:
        return a + np.clip(t, 0, 1) * r
    return None


def run_demo():
    points = np.array([[0., 0.], [1., 0.], [1., 1.], [0., 1.], [.5, .5]])
    transformed = rigid_transform(points, np.pi / 3, [2, -1])
    before = np.linalg.norm(points[:, None] - points[None, :], axis=-1)
    after = np.linalg.norm(transformed[:, None] - transformed[None, :], axis=-1)
    triangles = points[Delaunay(points).simplices]
    edges1, edges2 = triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    areas = np.abs(edges1[:, 0] * edges2[:, 1] - edges1[:, 1] * edges2[:, 0]) / 2
    voronoi = Voronoi(points)
    center_region = voronoi.regions[voronoi.point_region[4]]
    distance, index = KDTree(points).query([.1, .1])
    return {
        "distance_invariance_error": float(np.max(np.abs(before - after))),
        "intersection": segment_intersection([0, 0], [1, 1], [0, 1], [1, 0]).tolist(),
        "hull_area": float(ConvexHull(points).volume),
        "triangulated_area": float(areas.sum()), "minimum_triangle_area": float(areas.min()),
        "center_voronoi_is_bounded": bool(center_region and -1 not in center_region),
        "nearest_index": int(index), "nearest_distance": float(distance),
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, allow_nan=False))
