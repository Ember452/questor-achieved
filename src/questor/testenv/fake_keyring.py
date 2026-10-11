"""测试基建：内存 keyring 后端，替换 OS 凭据库。

只允许被测试 import（testenv 纪律同 fake_home）。用于 secrets 模块的
keyring 路径测试——真实 OS 凭据库在 CI 与开发者机器上行为各异，不可依赖。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import keyring
import keyring.errors
from keyring.backend import KeyringBackend


class FakeKeyring(KeyringBackend):
    """内存 keyring：接口与真后端一致，store 可直接断言。

    不设 ``priority``——经 ``keyring.set_keyring`` 直接安装，不走优先级竞选。
    """

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str | None) -> None:
        if password is None:
            raise ValueError("password 不能为 None（与真实后端一致地拒绝）")
        self.store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.store:
            raise keyring.errors.PasswordDeleteError(username)
        del self.store[(service, username)]


@contextmanager
def fake_keyring() -> Iterator[FakeKeyring]:
    """安装 fake keyring 并在退出时恢复原后端。"""
    backend = FakeKeyring()
    original = keyring.get_keyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(original)
