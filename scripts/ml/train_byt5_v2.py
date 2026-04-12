import os
import time
import random
import logging
import argparse
from pathlib import Path

import torch
import psycopg2
from typing import Any, Dict, List
from sklearn.model_selection import train_test_split

# HuggingFace & SOTA
from transformers import (
    AutoTokenizer, 
    AutoModelForSeq2SeqLM, 
    Seq2SeqTrainer, 
    Seq2SeqTrainingArguments,
    DataCollatorForSeq2Seq
)
from datasets import Dataset
from peft import LoraConfig, get_peft_model, TaskType

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

class ByT5V2Trainer:
    def __init__(self, model_name: str = "google/byt5-small", max_length: int = 128):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model_name = model_name
        self.max_length = max_length
        
    def _create_span_corruption_sample(self, text: str) -> Dict[str, str]:
        """
        Implements Scholarly Span Corruption using sentinel tokens.
        'suθi larθal' -> 'suθi <extra_id_0>al' / Target: '<extra_id_0> larθ <extra_id_1>'
        """
        if len(text) < 10 or "[" not in text or "]" not in text:
            # Fallback for synthetic training if no brackets exist
            if len(text) < 8: return {"input": text, "target": ""}
            start = random.randint(1, len(text) - 5)
            length = random.randint(2, 4)
            corrupted = text[:start] + "<extra_id_0>" + text[start+length:]
            target = f"<extra_id_0> {text[start:start+length]} <extra_id_1>"
            return {"input": corrupted, "target": target}
            
        # Real-world scholarly lacunae pattern [...], [---], [abc]
        # We find the bracketed part and mask it
        try:
            start_idx = text.find("[")
            end_idx = text.find("]")
            if start_idx != -1 and end_idx > start_idx:
                lacuna_content = text[start_idx+1:end_idx].replace(".", "").replace("-", "")
                if not lacuna_content: # Synthesize if empty brackets
                    lacuna_content = "???" 
                
                input_text = text[:start_idx] + "<extra_id_0>" + text[end_idx+1:]
                target_text = f"<extra_id_0> {lacuna_content} <extra_id_1>"
                return {"input": input_text, "target": target_text}
        except:
            pass
            
        return {"input": text, "target": ""}

    def train(self, db_url: str, output_dir: str, epochs: int = 5, batch_size: int = 2, accumulation_steps: int = 16):
        # 1. Fetch Data
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            # Fetch both clean verified and raw_text (to see brackets)
            cur.execute("SELECT raw_text, canonical FROM inscriptions WHERE provenance_status = 'verified'")
            rows = cur.fetchall()
        conn.close()
        
        # Prepare samples
        samples = []
        for raw, canonical in rows:
            if not raw or len(raw) < 5: continue
            sample = self._create_span_corruption_sample(raw)
            if sample["target"]:
                samples.append(sample)
        
        logger.info(f"Generated {len(samples)} span corruption samples.")
        
        train_data, val_data = train_test_split(samples, test_size=0.1, random_state=42)
        train_ds = Dataset.from_list(train_data)
        val_ds = Dataset.from_list(val_data)
        
        def tokenize_func(examples):
            model_inputs = self.tokenizer(examples["input"], max_length=self.max_length, truncation=True, padding="max_length")
            labels = self.tokenizer(text_target=examples["target"], max_length=64, truncation=True, padding="max_length")
            model_inputs["labels"] = labels["input_ids"]
            return model_inputs

        train_ds = train_ds.map(tokenize_func, batched=True)
        val_ds = val_ds.map(tokenize_func, batched=True)

        # 2. LoRA Prep
        model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
        lora_config = LoraConfig(
            r=8, 
            lora_alpha=32,
            target_modules=["q", "v"],
            lora_dropout=0.05,
            bias="none",
            task_type=TaskType.SEQ_2_SEQ_LM
        )
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()

        # 3. Training Args (6GB VRAM Optim)
        training_args = Seq2SeqTrainingArguments(
            output_dir=output_dir,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=accumulation_steps,
            learning_rate=2e-4,
            num_train_epochs=epochs,
            logging_steps=10,
            eval_strategy="epoch",
            save_strategy="epoch",
            fp16=True, # Turing optimized
            gradient_checkpointing=True, # Memory saving
            label_smoothing_factor=0.1,
            predict_with_generate=True,
            load_best_model_at_end=True,
            report_to="none"
        )

        trainer = Seq2SeqTrainer(
            model=model,
            args=training_args,
            train_dataset=train_ds,
            eval_dataset=val_ds,
            data_collator=DataCollatorForSeq2Seq(self.tokenizer, model=model)
        )

        logger.info("Starting ByT5 Intelligence V2 Training...")
        trainer.train()
        trainer.save_model(output_dir)
        logger.info(f"ByT5 V2 Exported to {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--output", default="data/models/byt5_v2")
    args = parser.parse_args()
    
    trainer = ByT5V2Trainer()
    trainer.train(args.db_url, args.output)
