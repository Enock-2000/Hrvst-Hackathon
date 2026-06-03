"""
NVIDIA LocateAnything-3B worker (CUDA).

Model: https://huggingface.co/nvidia/LocateAnything-3B
Demo:  https://huggingface.co/spaces/nvidia/LocateAnything
"""

from __future__ import annotations

import re

import torch
from PIL import Image


class LocateAnythingWorker:
    """Loads the model once and serves detection / grounding queries."""

    def __init__(
        self,
        model_path: str,
        device: str = "cuda",
        dtype: torch.dtype | None = None,
        attn_implementation: str = "sdpa",
    ):
        if not torch.cuda.is_available():
            raise RuntimeError(
                "LocateAnything requires CUDA. Install PyTorch with CUDA from https://pytorch.org/get-started/"
            )
        try:
            from transformers import AutoModel, AutoProcessor, AutoTokenizer
        except ImportError as e:
            raise ImportError(
                "Missing transformers. Run: pip install -r requirements-locateanything.txt"
            ) from e

        self.device = device if device.startswith("cuda") else "cuda"
        self.dtype = dtype or torch.bfloat16

        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        self.processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(
            model_path,
            torch_dtype=self.dtype,
            trust_remote_code=True,
            attn_implementation=attn_implementation,
        ).to(self.device).eval()

    @torch.no_grad()
    def predict(
        self,
        image: Image.Image,
        question: str,
        *,
        generation_mode: str = "hybrid",
        max_new_tokens: int = 2048,
        temperature: float = 0.7,
        verbose: bool = False,
    ) -> dict:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": question},
                ],
            }
        ]

        text = self.processor.py_apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        images, videos = self.processor.process_vision_info(messages)
        inputs = self.processor(
            text=[text], images=images, videos=videos, return_tensors="pt"
        ).to(self.device)

        pixel_values = inputs["pixel_values"].to(self.dtype)
        input_ids = inputs["input_ids"]
        image_grid_hws = inputs.get("image_grid_hws", None)

        response = self.model.generate(
            pixel_values=pixel_values,
            input_ids=input_ids,
            attention_mask=inputs["attention_mask"],
            image_grid_hws=image_grid_hws,
            tokenizer=self.tokenizer,
            max_new_tokens=max_new_tokens,
            use_cache=True,
            generation_mode=generation_mode,
            temperature=temperature,
            do_sample=True,
            top_p=0.9,
            repetition_penalty=1.1,
            verbose=verbose,
        )

        if isinstance(response, tuple):
            answer = response[0]
            result: dict = {"answer": answer}
            if len(response) >= 2:
                result["history"] = response[1]
            if len(response) >= 3:
                result["stats"] = response[2]
            return result

        return {"answer": response}

    def detect(self, image: Image.Image, categories: list[str], **kwargs) -> dict:
        cats = " ".join(categories)
        prompt = f"Locate all the instances that matches the following description: {cats}."
        return self.predict(image, prompt, **kwargs)

    @staticmethod
    def parse_boxes(answer: str, image_width: int, image_height: int) -> list[dict]:
        boxes = []
        for m in re.finditer(r"<box><(\d+)><(\d+)><(\d+)><(\d+)></box>", answer):
            x1, y1, x2, y2 = (int(g) for g in m.groups())
            boxes.append(
                {
                    "x1": x1 / 1000 * image_width,
                    "y1": y1 / 1000 * image_height,
                    "x2": x2 / 1000 * image_width,
                    "y2": y2 / 1000 * image_height,
                }
            )
        return boxes
