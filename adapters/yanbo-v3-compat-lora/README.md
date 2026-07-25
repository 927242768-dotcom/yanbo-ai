# 彦博-v3兼容适配器

该目录保存彦博-v3的正式兼容训练适配器，用于本地高性能服务不可用时的回退运行，以及表达风格、格式约束和专项能力补强。

## 当前版本

- 正式选择步数：700
- 第3轮起始步数：650
- 本轮实际尝试上限：750
- 选择原则：独立任务得分优先于单一验证损失
- 第3轮专项验证损失：2.3966 → 2.2848
- 原始兼容模型专项得分：7/18 → 8/18
- 正式引擎专项得分：7/18 → 18/18

750步候选虽然验证损失继续下降，但独立真实任务得分回落到7/18，因此没有发布。旧650步正式适配器已由提升脚本自动备份。

## 训练重点

- 严格数量、句数和成品输出；
- 信息不足时明确说明，不编造负责人、预算、日期或来源；
- 区分相关性与因果关系；
- 比例、平均数和基础多步计算；
- Python可变默认参数和边界处理；
- C格式化输出与缓冲区安全；
- Git取消暂存、SQL左连接与空组统计；
- OCR关键歧义处理；
- FPGA跨时钟域与测试边界。

## 文件

- `adapter_model.safetensors`：正式适配器权重；
- `adapter_config.json`：适配器配置；
- `training_state.json`：训练与最佳检查点状态；
- `adapter_release.json`：发布时间、哈希和来源清单。

## 验证

在项目根目录运行：

```text
python audit_training_data.py
python evaluate_training_upgrade.py --adapter adapters/yanbo-v3-compat-lora --execution raw
python evaluate_training_upgrade.py --adapter adapters/yanbo-v3-compat-lora --execution engine
python verify_identity.py
```

适配器只用于彦博-v3项目，不改变项目统一身份。
