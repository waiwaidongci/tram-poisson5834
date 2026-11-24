"""按数据批次类型分派校验与试算实现。"""

from . import analysis, connections

MODULES = {"blockage": analysis, "connections": connections}
