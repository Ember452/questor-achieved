"""Questor 测试基建（fake home / fake provider / fake git）。

只允许被测试 import——生产代码 import 本包视为架构违规
（tests/architecture/test_dependency_matrix.py 的反向规则由评审与后续 import-linter 契约保证）。
"""

__all__ = ["fake_home"]

from questor.testenv.fake_home import fake_home
