import pytest
from teela_core.navigation.path_planner import PathPlanner, GaitTarget


def test_path_planner_creation():
    planner = PathPlanner()
    assert planner.grid_res == 0.05


def test_astar_simple_path():
    planner = PathPlanner(grid_resolution_m=0.1)
    planner.update_occupancy([])
    path = planner.astar((0.0, 0.0), (1.0, 0.0))
    assert path is not None
    assert len(path) >= 2
    # Goal should be near (1.0, 0.0)
    assert abs(path[-1][0] - 1.0) < 0.15


def test_astar_blocked_path():
    planner = PathPlanner(grid_resolution_m=0.1)
    # Block the direct path
    planner.update_occupancy([(0.5, 0.0, 0.3)])
    path = planner.astar((0.0, 0.0), (1.0, 0.0))
    assert path is not None
    # Should go around
    assert max(abs(p[1]) for p in path) >= 0.15
