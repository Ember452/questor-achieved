"""e2e 公共夹具：每个用例一个隔离的 `QUESTOR_HOME`（不污染真实会话/编排记录）。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from questor.testenv.fake_home import fake_home


@pytest.fixture(autouse=True)
def _isolated_home() -> Iterator[None]:
    with fake_home():
        yield
