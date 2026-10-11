"""impl —— 八工具的具体实现（read/edit/write/list/search/todo/run/process）。

工具只声明参数与执行逻辑；授权判定由 executor 经 limen.gate 完成（工具摸不到门），
执行上下文（工作目录、文件状态缓存、进程管理器、todo 存储）经 ToolContext 注入。
"""
