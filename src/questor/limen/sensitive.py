"""敏感路径守卫：按段匹配 + 源码扩展名豁免（B-53）；写恒拒、unconfined 读降级脱敏（B-54）。

参照 wuu ``internal/tools/sensitive_paths.go``：判定按**路径段**而非整串子串——
``credentials.go`` 是认证源码不是凭据库（源码扩展名豁免），naive 子串匹配会误伤；
符号链接别名经调用方的 canonical resolve 后在这里看到的是真实段名，别名绕不过。

"凭据文件连 wuu 自己都摸不到"：Questor 自身配置（``~/.questor``）同样是敏感路径。
"""

from __future__ import annotations

import pathlib
import re

# 凭据类路径段（大小写不敏感）：目录或文件名命中即敏感
_CREDENTIAL_SEGMENTS = frozenset({"credential", "credentials", "secret", "secrets", ".netrc"})

# 私钥文件名前缀（精确名或其带后缀变体如 id_rsa.old）
_PRIVATE_KEY_PREFIXES = ("id_rsa", "id_ed25519", "id_ecdsa")

# 环境文件：.env 与 .env.*（.env.example 等模板豁免）
_ENV_PATTERN = re.compile(r"^\.env(\..+)?$")

# 源码扩展名豁免（B-53）：纯代码扩展——credentials.go 是认证源码。文档扩展
# （.md/.txt 等）刻意不在豁免内：凭据目录里的文档按敏感处理（fail-closed，
# 误伤文档的代价远小于放行凭据）。
_SOURCE_EXTENSIONS = (
    ".py",
    ".go",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".rs",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".rb",
    ".php",
    ".cs",
    ".swift",
    ".kt",
    ".scala",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
)

# 输出脱敏（B-54 unconfined 读降级）：KEY=value / "key": value / Bearer token
_REDACT_ASSIGNMENT = re.compile(
    r"(?i)^(\s*[A-Za-z0-9_.\-]*(?:key|token|secret|password|passwd|credential)[A-Za-z0-9_.\-]*\s*[=:]\s*)(\S.+)$"
)
_REDACT_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+\S+")


def classify(path_text: str) -> str | None:
    """返回敏感类别名；非敏感返回 ``None``。

    判定顺序：私钥名 → 环境文件 → 凭据段（源码扩展名豁免）。全部按段匹配，
    不做整串子串（B-53）。
    """
    pure = pathlib.PurePath(path_text)
    basename = pure.name.lower()
    if basename == ".netrc":
        return "netrc"
    for prefix in _PRIVATE_KEY_PREFIXES:
        if basename == prefix or (
            basename.startswith(prefix + ".") and not basename.endswith(".pub")
        ):
            return "private-key"  # .pub 公钥不敏感
    if _ENV_PATTERN.match(basename) and not basename.endswith(".example"):
        return "env-file"
    if basename.endswith(_SOURCE_EXTENSIONS):
        return None  # 源码豁免：credentials.go 是源码
    for part in pure.parts:
        if part.lower() in _CREDENTIAL_SEGMENTS:
            return "credential-path"
    return None


def write_blocked(path_text: str) -> bool:
    """敏感路径的**写**是否被拒——恒真（B-54：包括 unconfined 在内的一切档位）。"""
    return classify(path_text) is not None


def read_blocked(path_text: str, *, unconfined: bool) -> bool:
    """敏感路径的**读**是否被拒：unconfined 降级为脱敏放行（B-54），其余档位拒绝。"""
    if classify(path_text) is None:
        return False
    return not unconfined


def redact(text: str) -> str:
    """unconfined 读敏感路径时的输出脱敏（B-54）：逐行遮蔽赋值型凭据与 Bearer token。

    诚实边界：这是模式匹配降级，不是完整脱敏——无法保证识别所有秘密形态
    （overview §9："日志返回前脱敏，但声明不可完全识别"）。
    """
    lines: list[str] = []
    for line in text.splitlines():
        line = _REDACT_BEARER.sub(r"\1 [redacted]", line)
        line = _REDACT_ASSIGNMENT.sub(r"\1[redacted]", line)
        lines.append(line)
    return "\n".join(lines)
