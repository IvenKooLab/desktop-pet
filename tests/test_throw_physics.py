"""throw_physics 单元测试：速度估计、边缘反弹、落点与落定语义。"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import throw_physics


class EstimateVelocityTests(unittest.TestCase):
    def test_two_samples_give_speed(self):
        v = throw_physics.estimate_velocity(
            [(10.0, 100, 100), (10.1, 200, 100)], now=10.1)
        self.assertAlmostEqual(v[0], 1000.0, places=5)
        self.assertAlmostEqual(v[1], 0.0, places=5)

    def test_window_ignores_stale_samples(self):
        # 窗口外（>0.12s）的旧样本不参与估计
        v = throw_physics.estimate_velocity(
            [(10.0, 0, 0), (10.1, 500, 0), (10.15, 550, 0)], now=10.15)
        self.assertAlmostEqual(v[0], 1000.0, places=4)

    def test_too_short_span_is_none(self):
        self.assertIsNone(throw_physics.estimate_velocity(
            [(10.0, 100, 100), (10.005, 130, 100)], now=10.005))

    def test_insufficient_samples_is_none(self):
        self.assertIsNone(throw_physics.estimate_velocity([(10.0, 0, 0)], now=10.0))
        self.assertIsNone(throw_physics.estimate_velocity([], now=10.0))

    def test_speed_is_clamped(self):
        v = throw_physics.estimate_velocity(
            [(10.0, 0, 0), (10.1, 10000, 0)], now=10.1)
        self.assertAlmostEqual(math.hypot(*v), throw_physics.MAX_SPEED, places=3)

    def test_garbage_samples_ignored(self):
        self.assertIsNone(throw_physics.estimate_velocity(
            [(10.0, float("nan"), 0), (10.1, 10, 0)], now=10.1))


class StepTests(unittest.TestCase):
    def test_free_flight_falls(self):
        x, y, vx, vy, event = throw_physics.step(
            500, 100, 100, 0, 0.05, min_x=0, max_x=1000, min_y=0,
            ground_y=800, size=200)
        self.assertEqual(event, "fly")
        self.assertAlmostEqual(vy, throw_physics.G * 0.05)
        self.assertAlmostEqual(x, 500 + 100 * 0.05)

    def test_hard_impact_bounces_with_loss(self):
        _, y, _, vy, event = throw_physics.step(
            500, 500, 0, 1500, 0.25, min_x=0, max_x=1000, min_y=0,
            ground_y=800, size=200)
        self.assertEqual(event, "bounce")
        self.assertEqual(y, 600)                       # 贴面
        # 入射速度 1500 + 1200*0.25 = 1800，反弹 ×0.55
        self.assertAlmostEqual(vy, -(1500 + 1200 * 0.25) * throw_physics.RESTITUTION)

    def test_soft_impact_lands(self):
        # 贴面残余小速度（入射 180 + 重力增量 60 = 240 < 落定阈值）→ 直接停稳
        _, y, vx, vy, event = throw_physics.step(
            500, 600, 0, 180, 0.05, min_x=0, max_x=1000, min_y=0,
            ground_y=800, size=200)
        self.assertEqual(event, "land")
        self.assertEqual(y, 600)
        self.assertEqual((vx, vy), (0.0, 0.0))

    def test_side_edges_reflect(self):
        x, _, vx, _, _ = throw_physics.step(
            1990, 100, -3000, 0, 0.05, min_x=0, max_x=1800, min_y=0,
            ground_y=800, size=200)
        self.assertEqual(x, 1800)
        self.assertGreater(vx, 0)                      # 反弹回来

    def test_top_edge_reflects(self):
        _, y, _, vy, event = throw_physics.step(
            500, 5, 0, -2000, 0.02, min_x=0, max_x=1000, min_y=0,
            ground_y=800, size=200)
        self.assertEqual(y, 0)
        self.assertGreater(vy, 0)                      # 撞顶后向下
        self.assertEqual(event, "fly")

    def test_platform_catches_first(self):
        # 脚从 490 落过平台面 500：吸附平台而非更低的地面 800
        _, y, _, _, event = throw_physics.step(
            100, 290, 0, 800, 0.05, min_x=0, max_x=1000, min_y=0,
            ground_y=800, size=200, platforms=[(0, 500, 400), (0, 700, 400)])
        self.assertEqual(event, "bounce")
        self.assertEqual(y, 300)

    def test_invalid_inputs_are_noops(self):
        out = throw_physics.step(float("nan"), 0, 0, 0, 0.05,
                                 0, 100, 0, 800, 200)
        self.assertEqual(out[4], "fly")
        out = throw_physics.step(10, 10, 1, 1, 0, 0, 100, 0, 800, 200)
        self.assertEqual(out[:4], (10, 10, 1, 1))


if __name__ == "__main__":
    unittest.main()
