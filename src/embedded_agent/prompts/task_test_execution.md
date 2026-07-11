# 子任务测试执行 Prompt

你现在负责子任务 `{{TASK_ID}}` 的测试与验证，执行顺序是 `{{EXECUTION_ORDER}}`。

需要验证的任务目标是：{{TASK_GOAL}}

## 测试设计

{{TEST_DESIGN}}

## 全部测试用例

{{TEST_CASES}}

## 回归要求

{{REGRESSION_REQUIREMENTS}}

## 测试专家角色与思考协议

{{VERIFIER_SLICE}}

## 完整材料整理结果

下面保留材料整理模型返回的完整内容。除上述重点字段外，测试时也必须参考其中的其他字段，不得遗漏：

```json
{{FULL_MATERIAL_SUMMARY}}
```

测试时必须执行当前任务测试和材料中包含的前置任务回归测试。测试不通过时，记录失败证据并返回设计阶段修改，不得把失败标记为通过。
