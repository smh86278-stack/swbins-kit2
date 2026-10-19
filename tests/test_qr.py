# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import qr  # noqa: E402


class QrTest(unittest.TestCase):
    def test_reed_solomon(self):
        # 널리 쓰이는 예제(HELLO WORLD, 1-M)의 데이터·정정 코드워드
        data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17]
        self.assertEqual(qr._rs_remainder(data, qr._rs_divisor(10)), [196, 35, 39, 119, 235, 215, 231, 226, 93, 23])

    def test_tables(self):
        self.assertEqual(qr._align_positions(7), [6, 22, 38])
        self.assertEqual(qr._align_positions(10), [6, 28, 50])
        self.assertEqual(qr._data_codewords(1), 16)
        self.assertEqual(qr._data_codewords(10), 216)

    def test_matrix(self):
        m = qr.matrix("http://192.168.0.5:8653/")
        self.assertEqual(len(m), 25)                         # 버전 2
        for x, y in ((0, 0), (6, 0), (0, 6), (24, 0), (0, 24)):   # 찾기 패턴 모서리
            self.assertTrue(m[y][x])
        self.assertTrue(m[25 - 8][8])                        # 늘 검은 칸
        self.assertIn("<svg", qr.svg("x"))
        with self.assertRaises(ValueError):
            qr.matrix("x" * 400)


if __name__ == "__main__":
    unittest.main()
