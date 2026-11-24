# 002 数据批次类型

接驳影响试算引入第二类台账（班次到发、接驳余座、晚到更正），数据批次需要区分类型以分派校验与计算。

- `datasets` 新增 `kind` 列（`VARCHAR(20) NOT NULL DEFAULT 'blockage'`），取值 `blockage`（过车与阻断）或 `connections`（接驳对账）。
- 应用启动时先 `create_all` 补建缺失表，再检查 `information_schema`：既有 `datasets` 表缺 `kind` 列时执行 `ALTER TABLE` 补列，存量批次默认为 `blockage`。
- 导入时按 CSV 表头自动识别批次类型，同一批次的字段校验、运行参数与试算口径均按类型分派。
