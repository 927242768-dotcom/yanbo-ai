"""在 CPU 上对彦博当前版本的兼容模式进行轻量指令微调。"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from torch.utils.data import DataLoader, Dataset
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


class ChatSFTDataset(Dataset):
    def __init__(self, path: Path, tokenizer: Any, max_length: int) -> None:
        self.samples: list[tuple[list[int], list[int]]] = []
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

            # 当前高质量数据都很短；超长时保留末尾并重新计算监督起点。
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

        if not self.samples:
            raise ValueError(f"数据集为空或格式无效：{path}")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[list[int], list[int]]:
        return self.samples[index]


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
    max_batches: int = 20,
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


def save_adapter(model: torch.nn.Module, tokenizer: Any, output_dir: Path, state: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    (output_dir / "training_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"CPU 微调{DISPLAY_NAME}兼容模式")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--train-data", type=Path, default=Path("data/quality_sft_train.jsonl"))
    parser.add_argument("--val-data", type=Path, default=Path("data/quality_sft_val.jsonl"))
    parser.add_argument("--output", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--max-length", type=int, default=320)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--learning-rate", type=float, default=8e-5)
    parser.add_argument("--warmup-steps", type=int, default=2)
    parser.add_argument("--save-every", type=int, default=5)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if not args.model.exists():
        raise FileNotFoundError(f"没有找到模型：{args.model}，请先运行 python download_model.py")
    if not args.train_data.exists() or not args.val_data.exists():
        raise FileNotFoundError("没有找到高质量训练数据，请先运行 python build_quality_dataset.py")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
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

    state_path = args.output / "training_state.json"
    completed_steps = 0
    if args.resume and (args.output / "adapter_config.json").exists():
        model = PeftModel.from_pretrained(
            base_model,
            args.output,
            local_files_only=True,
            is_trainable=True,
        )
        if state_path.exists():
            completed_steps = int(json.loads(state_path.read_text(encoding="utf-8")).get("step", 0))
        print(f"从第 {completed_steps} 步继续训练")
    else:
        lora_config = LoraConfig(
            task_type="CAUSAL_LM",
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=["q_proj", "v_proj"],
            bias="none",
        )
        model = get_peft_model(base_model, lora_config)

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
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collator,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=collator,
    )
    print(f"训练样本：{len(train_dataset)}，验证样本：{len(val_dataset)}")

    trainable_parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable_parameters, lr=args.learning_rate, weight_decay=0.01)
    optimizer.zero_grad(set_to_none=True)

    step = completed_steps
    phase_total_steps = max(1, args.max_steps - completed_steps)
    phase_warmup_steps = min(args.warmup_steps, phase_total_steps)
    micro_step = 0
    running_loss = 0.0
    started = time.perf_counter()
    best_val = math.inf
    if state_path.exists():
        try:
            best_val = float(json.loads(state_path.read_text(encoding="utf-8")).get("best_val_loss", math.inf))
        except (OSError, ValueError, TypeError):
            best_val = math.inf

    while step < args.max_steps:
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
            phase_step = step - completed_steps
            if phase_step <= phase_warmup_steps:
                lr_scale = phase_step / max(1, phase_warmup_steps)
            else:
                progress = (phase_step - phase_warmup_steps) / max(1, phase_total_steps - phase_warmup_steps)
                lr_scale = 0.1 + 0.9 * 0.5 * (1.0 + math.cos(math.pi * progress))
            for group in optimizer.param_groups:
                group["lr"] = args.learning_rate * lr_scale
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)

            elapsed = time.perf_counter() - started
            print(
                f"step {step:3d}/{args.max_steps} | "
                f"loss {running_loss:.4f} | "
                f"lr {optimizer.param_groups[0]['lr']:.2e} | "
                f"{elapsed:.1f}s"
            )
            running_loss = 0.0

            if step % args.save_every == 0 or step == args.max_steps:
                val_loss = evaluate_loss(model, val_loader, device)
                best_val = min(best_val, val_loss)
                print(f"验证损失：{val_loss:.4f}")
                save_adapter(
                    model,
                    tokenizer,
                    args.output,
                    {
                        "step": step,
                        "max_steps": args.max_steps,
                        "val_loss": val_loss,
                        "best_val_loss": best_val,
                        "model": str(args.model),
                    },
                )
                print(f"{DISPLAY_NAME}兼容训练参数已保存。")

            if step >= args.max_steps:
                break

    print(f"微调完成，总耗时：{time.perf_counter() - started:.1f} 秒")


if __name__ == "__main__":
    main()
