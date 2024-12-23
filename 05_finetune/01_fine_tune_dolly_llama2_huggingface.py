#!/usr/bin/env python
# coding: utf-8

# # Requires p4d/p4de

# In[2]:


# %pip install transformers==4.31.0
# %pip install peft==0.4.0
# %pip install accelerate==0.21.0
#%pip install bitsandbytes==0.40.2
#%pip install safetensors==0.3.1
#%pip install tokenizers==0.13.3
# %pip install datasets==2.14.1

# %pip install -U transformers==4.39.0
# %pip install -U peft==0.5.0
# %pip install -U accelerate==0.26.0
# #%pip install bitsandbytes #==0.40.2
# #%pip install safetensors==0.3.1"
# #%pip install tokenizers==0.13.3
# %pip install -U datasets==2.17.0
# %pip install --no-cache https://developer.download.nvidia.com/compute/redist/jp/v60dp/pytorch/torch-2.3.0a0+ebedce2.nv24.02-cp310-cp310-linux_aarch64.whl

# In[3]:


import os
import argparse
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    set_seed,
    default_data_collator,
#    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
)
from datasets import load_dataset
import torch

#import bitsandbytes as bnb
#from huggingface_hub import login, HfFolder

# ## Fine-Tune LLaMA 7B in Amazon SageMaker Studio

# In[4]:


import argparse
parser = argparse.ArgumentParser()

# add model id and dataset path argument
parser.add_argument(
    "--model_id",
    type=str,
    default="NousResearch/Llama-2-7b-hf", # not gated
    help="Model id to use for training.",
)
parser.add_argument(
    "--dataset_path", 
    type=str, 
    default="lm_dataset", 
    help="Path to dataset."
)
# parser.add_argument(
#     "--hf_token", 
#     type=str, 
#     default=HfFolder.get_token(), 
#     help="Path to dataset."
# )
# add training hyperparameters for epochs, batch size, learning rate, and seed
parser.add_argument(
    "--epochs", 
    type=int, 
    default=1, 
    help="Number of epochs to train for."
)
parser.add_argument(
    "--per_device_train_batch_size",
    type=int,
    default=1,
    help="Batch size to use for training.",
)
parser.add_argument(
    "--lr", 
    type=float, 
    default=5e-5, 
    help="Learning rate to use for training."
)
parser.add_argument(
    "--seed", 
    type=int, 
    default=42, 
    help="Seed to use for training."
)
parser.add_argument(
    "--gradient_checkpointing",
    type=bool,
    default=True,
    help="Path to deepspeed config file.",
)
parser.add_argument(
    "--bf16",
    type=bool,
    default=True if torch.cuda.get_device_capability()[0] >= 8 else False,
    help="Whether to use bf16.",
)
# parser.add_argument(
#     "--merge_weights",
#     type=bool,
#     default=True,
#     help="Whether to merge LoRA weights with base model.",
# )
args, _ = parser.parse_known_args()

# if args.hf_token:
#     print(f"Logging into the Hugging Face Hub with token {args.hf_token[:10]}...")
#     login(token=args.hf_token)

# In[5]:


# # COPIED FROM https://github.com/artidoro/qlora/blob/main/qlora.py
# def print_trainable_parameters(model, use_4bit=False):
#     """
#     Prints the number of trainable parameters in the model.
#     """
#     trainable_params = 0
#     all_param = 0
#     for _, param in model.named_parameters():
#         num_params = param.numel()
#         # if using DS Zero 3 and the weights are initialized empty        
#         if num_params == 0 and hasattr(param, "ds_numel"):
#             num_params = param.ds_numel

#         all_param += num_params
#         if param.requires_grad:
#             trainable_params += num_params
#     # if use_4bit:
#     #     trainable_params /= 2
#     print(
#         f"all params: {all_param:,d} || trainable params: {trainable_params:,d} || trainable%: {100 * trainable_params / all_param}"
#     )


# # # COPIED FROM https://github.com/artidoro/qlora/blob/main/qlora.py
# # def find_all_linear_names(model):
# #     lora_module_names = set()
# # #    for name, module in model.named_modules():
# #         # if isinstance(module, bnb.nn.Linear4bit):
# #         #     names = name.split(".")
# #         #     lora_module_names.add(names[0] if len(names) == 1 else names[-1])

# #     if "lm_head" in lora_module_names:  # needed for 16-bit
# #         lora_module_names.remove("lm_head")
# #     return list(lora_module_names)


# def create_peft_model(model, gradient_checkpointing=True, bf16=True):
#     from peft import (
#         get_peft_model,
#         LoraConfig,
#         TaskType,
# #        prepare_model_for_kbit_training,
#     )
#     from peft.tuners.lora import LoraLayer

#     # # prepare int-4 model for training
#     # model = prepare_model_for_kbit_training(
#     #     model, use_gradient_checkpointing=gradient_checkpointing
#     # )
#     if gradient_checkpointing:
#         model.gradient_checkpointing_enable()

#     # # get lora target modules
#     # modules = find_all_linear_names(model)    
    
#     #If only targeting attention blocks of the model
#     #modules = ["q_proj", "v_proj"]

#     #If targeting all linear layers
#     modules = ['q_proj','k_proj','v_proj','o_proj','gate_proj','down_proj','up_proj'] #,'lm_head']

#     print(f"Found {len(modules)} modules to quantize: {modules}")

#     peft_config = LoraConfig(
#         r=64,
#         lora_alpha=16,
#         target_modules=modules,
#         lora_dropout=0.1,
#         bias="none",
#         task_type=TaskType.CAUSAL_LM,
#     )

#     model = get_peft_model(model, peft_config)

#     # pre-process the model by upcasting the layer norms in float 32 for
#     # for name, module in model.named_modules():
#     #     if isinstance(module, LoraLayer):
#     #         if bf16:
#     #             module = module.to(torch.bfloat16)
#     #     if "norm" in name:
#     #         module = module.to(torch.float32)
#     #     if "lm_head" in name or "embed_tokens" in name:
#     #         if hasattr(module, "weight"):
#     #             if bf16 and module.weight.dtype == torch.float32:
#     #                 module = module.to(torch.bfloat16)

#     model.print_trainable_parameters()
#     return model

# ## Load and prepare the dataset
# 
# we will use the [dolly](https://huggingface.co/datasets/databricks/databricks-dolly-15k) an open source dataset of instruction-following records generated by thousands of Databricks employees in several of the behavioral categories outlined in the [InstructGPT paper](https://arxiv.org/abs/2203.02155), including brainstorming, classification, closed QA, generation, information extraction, open QA, and summarization.
# 
# ```python
# {
#   "instruction": "What is world of warcraft",
#   "context": "",
#   "response": "World of warcraft is a massive online multi player role playing game. It was released in 2004 by bizarre entertainment"
# }
# ```
# 
# To load the `samsum` dataset, we use the `load_dataset()` method from the 🤗 Datasets library.

# In[6]:


# set seed
set_seed(args.seed)

from datasets import load_dataset
from random import randrange

# Load dataset from the hub
dataset = load_dataset("databricks/databricks-dolly-15k", split="train")
dataset = dataset.select(range(1000))

print(f"dataset size: {len(dataset)}")
print(dataset[randrange(len(dataset))])
# dataset size: 15011

# To instruct tune our model we need to convert our structured examples into a collection of tasks described via instructions. We define a `formatting_function` that takes a sample and returns a string with our format instruction.

# In[7]:


def format_dolly(sample):
    instruction = f"### Instruction\n{sample['instruction']}"
    context = f"### Context\n{sample['context']}" if len(sample["context"]) > 0 else None
    response = f"### Answer\n{sample['response']}"
    # join all the parts together
    prompt = "\n\n".join([i for i in [instruction, context, response] if i is not None])
    return prompt


# In[8]:


from random import randrange

print(format_dolly(dataset[randrange(len(dataset))]))

# In[9]:


from transformers import AutoTokenizer

#model_id = "meta-llama/Llama-2-13b-hf" # sharded weights, gated
model_id = "NousResearch/Llama-2-7b-hf" # not gated
tokenizer = AutoTokenizer.from_pretrained(model_id)
tokenizer.pad_token = tokenizer.eos_token

# In[10]:


from random import randint
from itertools import chain
from functools import partial


# template dataset to add prompt to each sample
def template_dataset(sample):
    sample["text"] = f"{format_dolly(sample)}{tokenizer.eos_token}"
    return sample


# apply prompt template per sample
dataset = dataset.map(template_dataset, remove_columns=list(dataset.features))
# print random sample
print(dataset[randint(0, len(dataset))]["text"])

# empty list to save remainder from batches to use in next batch
remainder = {"input_ids": [], "attention_mask": [], "token_type_ids": []}

def chunk(sample, chunk_length=2048):
    # define global remainder variable to save remainder from batches to use in next batch
    global remainder
    # Concatenate all texts and add remainder from previous batch
    concatenated_examples = {k: list(chain(*sample[k])) for k in sample.keys()}
    concatenated_examples = {k: remainder[k] + concatenated_examples[k] for k in concatenated_examples.keys()}
    # get total number of tokens for batch
    batch_total_length = len(concatenated_examples[list(sample.keys())[0]])

    # get max number of chunks for batch
    if batch_total_length >= chunk_length:
        batch_chunk_length = (batch_total_length // chunk_length) * chunk_length

    # Split by chunks of max_len.
    result = {
        k: [t[i : i + chunk_length] for i in range(0, batch_chunk_length, chunk_length)]
        for k, t in concatenated_examples.items()
    }
    # add remainder to global variable for next batch
    remainder = {k: concatenated_examples[k][batch_chunk_length:] for k in concatenated_examples.keys()}
    # prepare labels
    result["labels"] = result["input_ids"].copy()
    return result


# tokenize and chunk dataset
lm_dataset = dataset.map(
    lambda sample: tokenizer(sample["text"]), batched=True, remove_columns=list(dataset.features)
).map(
    partial(chunk, chunk_length=2048),
    batched=True,
)

# Print total number of samples
print(f"Total number of samples: {len(lm_dataset)}")

# In[11]:


# The chunking above will reduce the number of rows
print(lm_dataset)

# In[12]:


# load model from the hub with a bnb config
# bnb_config = BitsAndBytesConfig(
#     load_in_4bit=True,
#     bnb_4bit_use_double_quant=True,
#     bnb_4bit_quant_type="nf4",
#     bnb_4bit_compute_dtype=torch.bfloat16,
# )

model = AutoModelForCausalLM.from_pretrained(
    args.model_id,
    use_cache=False
    if args.gradient_checkpointing
    else True,  # this is needed for gradient checkpointing
    device_map="auto",
#    quantization_config=bnb_config,
)

# create peft config
# model = create_peft_model(
#     model, gradient_checkpointing=args.gradient_checkpointing, bf16=args.bf16
# )

# In[13]:


# Define training args
output_dir = "./tmp/llama2"
training_args = TrainingArguments(
    output_dir=output_dir,
    per_device_train_batch_size=args.per_device_train_batch_size,
    bf16=args.bf16,  # Use BF16 if available
    learning_rate=args.lr,
    num_train_epochs=args.epochs,
    gradient_checkpointing=args.gradient_checkpointing,
    # logging strategies
    logging_dir=f"{output_dir}/logs",
    logging_strategy="steps",
    logging_steps=10,
    save_strategy="no",
)

# Create Trainer instance
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=lm_dataset,
    data_collator=default_data_collator,
)

# Start training
trainer.train()

# In[14]:


sagemaker_save_dir="./llama2_dolly"
# if args.merge_weights:
#     # merge adapter weights with base model and save
#     # save int 4 model
#     trainer.model.save_pretrained(output_dir, safe_serialization=False)
#     # clear memory
#     del model
#     del trainer
#     torch.cuda.empty_cache()

#     from peft import AutoPeftModelForCausalLM

#     # load PEFT model in fp16
#     model = AutoPeftModelForCausalLM.from_pretrained(
#         output_dir,
#         low_cpu_mem_usage=True,
#         torch_dtype=torch.bfloat16,
#     )  
#     # Merge LoRA and base model and save
#     model = model.merge_and_unload()        
#     model.save_pretrained(
#         sagemaker_save_dir, safe_serialization=True, max_shard_size="2GB"
#     )
# else:

trainer.model.save_pretrained(
    sagemaker_save_dir, safe_serialization=True
)

# save tokenizer for easy inference
tokenizer = AutoTokenizer.from_pretrained(args.model_id)
tokenizer.save_pretrained(sagemaker_save_dir)

# In[ ]:



