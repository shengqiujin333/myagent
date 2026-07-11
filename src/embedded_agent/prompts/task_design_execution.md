# 子任务设计执行 Prompt

你现在负责子任务 `{{TASK_ID}}`，执行顺序是 `{{EXECUTION_ORDER}}`。

你的任务目标是：{{TASK_GOAL}}

你需要依据下面的设计材料完成实现设计，并在目标工程中增量实现功能：

## 设计目标

{{DESIGN_OBJECTIVE}}

## 详细设计范围

{{DETAILED_DESIGN_SCOPE}}

## 目标文件与资源

{{TARGET_FILES}}

## 兼容性要求

{{COMPATIBILITY_STRATEGY}}

## 设计专家角色与思考协议

{{DESIGNER_SLICE}}

## 完整材料整理结果

下面保留材料整理模型返回的完整内容。除上述重点字段外，执行时也必须参考其中的其他字段，不得遗漏：

```json
{{FULL_MATERIAL_SUMMARY}}
```

实现时必须保留已有功能。新功能与旧功能冲突时，先分析冲突并采用兼容或隔离方案，再继续实现。

完成实现后，将由对应测试材料驱动验证；不要自行跳过已有功能的兼容性考虑。
