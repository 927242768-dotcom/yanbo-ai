"""对彦博-v3兼容模型执行可验证、可回滚的LoRA指令微调。"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from transformers import AutoModelForCausalLM, AutoTokenizer

from assistant_engine import DEFAULT_ADAPTER_PATH, DEFAULT_MODEL_PATH, DISPLAY_NAME
from console_utils import configure_utf8_console


IGNORE_INDEX = -100


def _extract_ids(value: Any) -> list[int]:
    if isinstance(value, dict):
        value = value["input_ids"]
    elif hasattr(value, "data") and "input_ids" in value:
        value = value["input_ids"]
    if isinstance(value, torch.Tensor):
        value = value.tolist()
    if value and isinstance(value[0], list):
        value = value[0]
    return [int(token) for token in value]


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


class ChatSFTDataset(Dataset):
    def __init__(self, path: Path, tokenizer: Any, max_length: int) -> None:
        self.samples: list[tuple[list[int], list[int]]] = []
        self.categories: list[str] = []
        with path.open("r", encoding="utf-8") as file:
            rows = [json.loads(line) for line in file if line.strip()]

        for row in rows:
            messages = row.get("messages", [])
            if len(messages) < 2 or messages[-1].get("role") != "assistant":
                continue
            prompt_messages = messages[:-1]
            prompt_ids = _extract_ids(
                tokenizer.apply_chat_template(
                    prompt_messages,
                    tokenize=True,
                    add_generation_prompt=True,
                )
            )
            full_ids = _extract_ids(
                tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=False,
                )
            )

            # 超长样本保留末尾，并同步移动监督起点，避免把用户提示当作标签训练。
            if len(full_ids) > max_length:
                removed = len(full_ids) - max_length
                full_ids = full_ids[removed:]
                prompt_length = max(0, len(prompt_ids) - removed)
            else:
                prompt_length = min(len(prompt_ids), len(full_ids))

            labels = [IGNORE_INDEX] * prompt_length + full_ids[prompt_length:]
            if not labels or all(label == IGNORE_INDEX for label in labels):
                continue
            self.samples.append((full_ids, labels))
            self.categories.append(str(row.get("category", "general")))

        if not self.samples:
            raise ValueError(f"数据集为空或格式无效：{path}")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[list[int], list[int]]:
        return self.samples[index]

    @property
    def category_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(self.categories).items()))

    def balanced_weights(self) -> list[float]:
        """按类别频次平方根反比采样，缓解大类压制小类，同时避免极端过采样。"""
        counts = Counter(self.categories)
        return [1.0 / math.sqrt(counts[category]) for category in self.categories]


@dataclass
class DataCollator:
    pad_token_id: int

    def __call__(self, batch: list[tuple[list[int], list[int]]]) -> dict[str, torch.Tensor]:
        max_length = max(len(input_ids) for input_ids, _ in batch)
        input_batch: list[list[int]] = []
        label_batch: list[list[int]] = []
        mask_batch: list[list[int]] = []
        for input_ids, labels in batch:
            padding = max_length - len(input_ids)
            input_batch.append(input_ids + [self.pad_token_id] * padding)
            label_batch.append(labels + [IGNORE_INDEX] * padding)
            mask_batch.append([1] * len(input_ids) + [0] * padding)
        return {
            "input_ids": torch.tensor(input_batch, dtype=torch.long),
            "labels": torch.tensor(label_batch, dtype=torch.long),
            "attention_mask": torch.tensor(mask_batch, dtype=torch.long),
        }


def evaluate_loss(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
    max_batches: int = 40,
) -> float:
    model.eval()
    losses: list[float] = []
    with torch.inference_mode():
        for index, batch in enumerate(loader):
            if index >= max_batches:
                break
            batch = {key: value.to(device) for key, value in batch.items()}
            output = model(**batch)
            losses.append(float(output.loss.detach().cpu()))
    model.train()
    return sum(losses) / max(1, len(losses))


def trainable_snapshot(model: torch.nn.Module) -> dict[str, torch.Tensor]:
    return {
        name: parameter.detach().cpu().clone()
        for name, parameter in model.named_parameters()
        if parameter.requires_grad
    }


def restore_trainable_snapshot(
    model: torch.nn.Module,
    snapshot: dict[str, torch.Tensor],
) -> None:
    parameters = dict(model.named_parameters())
    with torch.no_grad():
        for name, value in snapshot.items():
            if name not in parameters:
                raise KeyError(f"最佳检查点缺少参数：{name}")
            parameters[name].copy_(value.to(parameters[name].device))


def save_adapter(
    model: torch.nn.Module,
    tokenizer: Any,
    output_dir: Path,
    state: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    (output_dir / "training_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"高质量微调{DISPLAY_NAME}兼容模式")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--train-data", type=Path, default=Path("data/quality_sft_train.jsonl"))
    parser.add_argument("--val-data", type=Path, default=Path("data/quality_sft_val.jsonl"))
    parser.add_argument("--output", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument(
        "--init-adapter",
        type=Path,
        help="从另一个适配器初始化，但把训练结果写入--output，便于候选模型对比和回滚",
    )
    parser.add_argument("--max-length", type=int, default=384)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--warmup-steps", type=int, default=4)
    parser.add_argument("--save-every", type=int, default=10)
    parser.add_argument("--val-batches", type=int, default=40)
    parser.add_argument("--early-stopping-patience", type=int, default=6)
    parser.add_argument("--min-delta", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument(
        "--target-modules",
        default="q_proj,v_proj",
        help="逗号分隔的LoRA目标模块；仅新建适配器时生效",
    )
    parser.add_argument(
        "--no-balanced-sampling",
        action="store_true",
        help="关闭按类别平衡的训练采样",
    )
    args = parser.parse_args()

    if not args.model.exists():
        raise FileNotFoundError(f"没有找到模型：{args.model}，请先运行python download_model.py")
    if not args.train_data.exists() or not args.val_data.exists():
        raise FileNotFoundError("没有找到训练数据，请先构建并审计数据集")
    if args.max_steps <= 0 or args.grad_accum <= 0 or args.save_every <= 0:
        raise ValueError("训练步数、梯度累积和保存间隔必须大于0")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(max(1, min(12, os.cpu_count() or 1)))
    try:
        torch.set_float32_matmul_precision("high")
    except (AttributeError, RuntimeError):
        pass
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"设备：{device}")
    print(f"正在加载{DISPLAY_NAME}兼容训练组件……")

    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    base_model = AutoModelForCausalLM.from_pretrained(
        args.model,
        local_files_only=True,
        low_cpu_mem_usage=True,
        dtype=torch.float32 if device.type == "cpu" else torch.float16,
    )
    base_model.config.use_cache = False

    resume_source: Path | None = None
    if args.resume and (args.output / "adapter_config.json").exists():
        resume_source = args.output
    elif args.init_adapter and (args.init_adapter / "adapter_config.json").exists():
        resume_source = args.init_adapter

    completed_steps = 0
    source_state: dict[str, Any] = {}
    if resume_source is not None:
        model = PeftModel.from_pretrained(
            base_model,
            resume_source,
            local_files_only=True,
            is_trainable=True,
        )
        source_state = _load_state(resume_source / "training_state.json")
        completed_steps = int(source_state.get("step", 0) or 0)
        print(f"从适配器{resume_source}的第{completed_steps}步继续训练")
    else:
        target_modules = [
            module.strip() for module in args.target_modules.split(",") if module.strip()
        ]
        if not target_modules:
            raise ValueError("--target-modules不能为空")
        lora_config = LoraConfig(
            task_type="CAUSAL_LM",
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            target_modules=target_modules,
            bias="none",
        )
        model = get_peft_model(base_model, lora_config)
        print(
            f"新建LoRA：r={args.lora_r}，alpha={args.lora_alpha}，"
            f"targets={','.join(target_modules)}"
        )

    if args.max_steps <= completed_steps:
        raise ValueError(
            f"--max-steps={args.max_steps}必须大于当前已完成步数{completed_steps}"
        )

    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    if hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()
    model.to(device)
    model.train()
    model.print_trainable_parameters()

    train_dataset = ChatSFTDataset(args.train_data, tokenizer, args.max_length)
    val_dataset = ChatSFTDataset(args.val_data, tokenizer, args.max_length)
    collator = DataCollator(tokenizer.pad_token_id)
    generator = torch.Generator().manual_seed(args.seed + completed_steps)
    if args.no_balanced_sampling:
        train_loader = DataLoader(
            train_dataset,
            batch_size=args.batch_size,
            shuffle=True,
            generator=generator,
            collate_fn=collator,
        )
        sampling_mode = "随机打乱"
    else:
        sampler = WeightedRandomSampler(
            train_dataset.balanced_weights(),
            num_samples=len(train_dataset),
            replacement=True,
            generator=generator,
        )
        train_loader = DataLoader(
            train_dataset,
            batch_size=args.batch_size,
            sampler=sampler,
            collate_fn=collator,
        )
        sampling_mode = "类别平方根平衡采样"
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=collator,
    )
    print(f"训练样本：{len(train_dataset)}，验证样本：{len(val_dataset)}")
    print(f"训练采样：{sampling_mode}")
    print("训练类别：" + json.dumps(train_dataset.category_counts, ensure_ascii=False))

    trainable_parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(
        trainable_parameters,
        lr=args.learning_rate,
        weight_decay=0.01,
        betas=(0.9, 0.95),
    )
    optimizer.zero_grad(set_to_none=True)

    print("正在测量本阶段训练前验证损失……")
    initial_val = evaluate_loss(model, val_loader, device, max_batches=args.val_batches)
    print(f"阶段初始验证损失：{initial_val:.4f}")
    best_val = initial_val
    best_step = completed_steps
    best_state = trainable_snapshot(model)
    no_improvement = 0
    history: list[dict[str, Any]] = [
        {"step": completed_steps, "val_loss": initial_val, "selected": True}
    ]

    step = completed_steps
    attempted_step = completed_steps
    phase_total_steps = max(1, args.max_steps - completed_steps)
    phase_warmup_steps = min(args.warmup_steps, phase_total_steps)
    micro_step = 0
    running_loss = 0.0
    started = time.perf_counter()
    stop_training = False

    while step < args.max_steps and not stop_training:
        for batch in train_loader:
            batch = {key: value.to(device) for key, value in batch.items()}
            output = model(**batch)
            loss = output.loss / args.grad_accum
            loss.backward()
            running_loss += float(loss.detach().cpu())
            micro_step += 1

            if micro_step % args.grad_accum != 0:
                continue

            torch.nn.utils.clip_grad_norm_(trainable_parameters, 1.0)
            step += 1
            attempted_step = step
            phase_step = step - completed_steps
            if phase_step <= phase_warmup_steps:
                lr_scale = phase_step / max(1, phase_warmup_steps)
            else:
                progress = (phase_step - phase_warmup_steps) / max(
                    1, phase_total_steps - phase_warmup_steps
                )
                lr_scale = 0.1 + 0.9 * 0.5 * (1.0 + math.cos(math.pi * progress))
            for group in optimizer.param_groups:
                group["lr"] = args.learning_rate * lr_scale
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)

            elapsed = time.perf_counter() - started
            print(
                f"step {step:4d}/{args.max_steps} | "
                f"loss {running_loss:.4f} | "
                f"lr {optimizer.param_groups[0]['lr']:.2e} | "
                f"{elapsed:.1f}s",
                flush=True,
            )
            running_loss = 0.0

            if step % args.save_every == 0 or step == args.max_steps:
                val_loss = evaluate_loss(
                    model,
                    val_loader,
                    device,
                    max_batches=args.val_batches,
                )
                improved = val_loss < best_val - args.min_delta
                if improved:
                    best_val = val_loss
                    best_step = step
                    best_state = trainable_snapshot(model)
                    no_improvement = 0
                else:
                    no_improvement += 1
                history.append(
                    {"step": step, "val_loss": val_loss, "selected": improved}
                )
                print(
                    f"验证损失：{val_loss:.4f} | 最佳：{best_val:.4f}@{best_step} | "
                    f"连续未提升：{no_improvement}/{args.early_stopping_patience}",
                    flush=True,
                )
                checkpoint_state = {
                    "step": step,
                    "attempted_step": attempted_step,
                    "max_steps": args.max_steps,
                    "val_loss": val_loss,
                    "best_val_loss": best_val,
                    "best_step": best_step,
                    "initial_val_loss": initial_val,
                    "model": str(args.model),
                    "initialized_from": str(resume_source) if resume_source else "",
                    "sampling_mode": sampling_mode,
                    "category_counts": train_dataset.category_counts,
                    "history": history,
                    "selected_checkpoint": "latest_in_progress",
                }
                save_adapter(model, tokenizer, args.output, checkpoint_state)
                print(f"候选检查点已保存到{args.output}。", flush=True)

                if (
                    args.early_stopping_patience > 0
                    and no_improvement >= args.early_stopping_patience
                ):
                    print("验证损失连续未提升，触发提前停止。", flush=True)
                    stop_training = True
                    break

            if step >= args.max_steps:
                break

    restore_trainable_snapshot(model, best_state)
    final_state = {
        "step": best_step,
        "attempted_step": attempted_step,
        "max_steps": args.max_steps,
        "val_loss": best_val,
        "best_val_loss": best_val,
        "best_step": best_step,
        "initial_val_loss": initial_val,
        "model": str(args.model),
        "initialized_from": str(resume_source) if resume_source else "",
        "sampling_mode": sampling_mode,
        "category_counts": train_dataset.category_counts,
        "history": history,
        "selected_checkpoint": "best_validation",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    save_adapter(model, tokenizer, args.output, final_state)
    print(
        f"微调结束：尝试到第{attempted_step}步，最终选择第{best_step}步，"
        f"验证损失{initial_val:.4f} -> {best_val:.4f}。"
    )
    print(f"总耗时：{time.perf_counter() - started:.1f}秒")


if __name__ == "__main__":
    main()
