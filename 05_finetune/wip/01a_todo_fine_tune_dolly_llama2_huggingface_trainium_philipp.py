#!/usr/bin/env python
# coding: utf-8

# # Fine-tune Llama on AWS Trainium 
# 
# This tutorial will teach how to fine-tune open LLMs like [Llama 2](https://huggingface.co/meta-llama/Llama-2-70b-hf) on AWS Trainium.  In our example, we are going to leverage Hugging Face Optimum Neuron, [Transformers](https://huggingface.co/docs/transformers/index)and datasets. 
# 
# You will learn how to:
# 
# 1. [Setup AWS environment](#1-setup-aws-environment)
# 2. [Load and process the dataset](#2-load-and-prepare-the-dataset)
# 3. [Fine-tune Llama on AWS Trainium using the `NeuronTrainer`](#3-fine-tune-llama-on-aws-trainium-using-the-neurontrainer)
# 4. [Evalaute and test fine-tuned Llama model](#4-evalaute-and-test-fine-tuned-llama-model)
# 
# ## Quick intro: AWS Trainium
# 
# [AWS Trainium (Trn1)](https://aws.amazon.com/de/ec2/instance-types/trn1/) is a purpose-built EC2 for deep learning (DL) training workloads. Trainium is the successor of [AWS Inferentia](https://aws.amazon.com/ec2/instance-types/inf1/?nc1=h_ls) focused on high-performance training workloads. Trainium has been optimized for training natural language processing, computer vision, and recommender models used. The accelerator supports a wide range of data types, including FP32, TF32, BF16, FP16, UINT8, and configurable FP8. 
# 
# The biggest Trainium instance, the `trn1.32xlarge` comes with over 500GB of memory, making it easy to fine-tune ~10B parameter models on a single instance. Below you will find an overview of the available instance types. More details [here](https://aws.amazon.com/de/ec2/instance-types/trn1/#Product_details):
# 
# | instance size | accelerators | accelerator memory | vCPU | CPU Memory | price per hour |
# | --- | --- | --- | --- | --- | --- |
# | trn1.2xlarge | 1 | 32 | 8 | 32 | \$1.34 |
# | trn1.32xlarge | 16 | 512 | 128 | 512 | \$21.50 |
# | trn1n.32xlarge (2x bandwidth) | 16 | 512 | 128 | 512 | \$24.78 |
# 
# ---
# 
# *Note: This tutorial was created on a trn1.32xlarge AWS EC2 Instance.* 
# 
# 
# ## 1. Setup AWS environment
# 
# In this example, we will use the `trn1.32xlarge` instance on AWS with 16 Accelerator, including 32 Neuron Cores and the [Hugging Face Neuron Deep Learning AMI](https://aws.amazon.com/marketplace/pp/prodview-gr3e6yiscria2). The Hugging Face AMI comes with all important libraries, like Transformers, Datasets, Optimum and Neuron packages pre-installed this makes it super easy to get started, since there is no need for environment management.
# 
# This blog post doesn’t cover how to create the instance in detail. You can check out my previous blog about [“Setting up AWS Trainium for Hugging Face Transformers”](https://www.philschmid.de/setup-aws-trainium), which includes a step-by-step guide on setting up the environment. 
# 
# Once the instance is up and running, we can ssh into it. But instead of developing inside a terminal we want to use a `Jupyter` environment, which we can use for preparing our dataset and launching the training. For this, we need to add a port for forwarding in the `ssh` command, which will tunnel our localhost traffic to the Trainium instance.
# 
# ```bash
# PUBLIC_DNS="" # IP address, e.g. ec2-3-80-....
# KEY_PATH="" # local path to key, e.g. ssh/trn.pem
# 
# ssh -L 8080:localhost:8080 -i ${KEY_NAME}.pem ubuntu@$PUBLIC_DNS
# ```
# 
# Lets now pull the optimum repository with the [example notebook and scripts](https://github.com/huggingface/optimum-neuron/tree/main/notebooks/text-generation).
# 
# ```bash
# git clone https://github.com/huggingface/optimum-neuron.git
# ```
# 
# Next we can change our directory to `notbooks/text-generation` and launch the `jupyter` environment.``
# 
# 
# ```bash
# # change directory
# cd optimum-neuron/notebooks/text-generation
# # launch jupyter
# python -m notebook --allow-root --port=8080
# ```
# 
# You should see a familiar **`jupyter`** output with a URL to the notebook.
# 
# **`http://localhost:8080/?token=8c1739aff1755bd7958c4cfccc8d08cb5da5234f61f129a9`**
# 
# We can click on it, and a **`jupyter`** environment opens in our local browser. Open the notebook **`llama2-7b-fine-tuning.ipynb`** and lets get started.
# 
# _Note: We are going to use the Jupyter environment only for preparing the dataset and then `torchrun` for launching our training script for  distributed training._

# In[4]:


%pip install optimum-neuron torch-neuronx

# If you are going to use official Llama 2 checkpoint you need to login into our hugging face account, which has access to the model, to use your token for accessing the gated repository. We can do this by running the following command:
# 
# _Note: We also provide an ungated checkpoint._

# In[2]:


# !huggingface-cli login --token YOUR_TOKEN

# ## 2. Load and prepare the dataset
# 
# We will use [Dolly](https://huggingface.co/datasets/databricks/databricks-dolly-15k) an open source dataset of instruction-following records on categories outlined in the [InstructGPT paper](https://arxiv.org/abs/2203.02155), including brainstorming, classification, closed QA, generation, information extraction, open QA, and summarization.
# 
# ```python
# {
#   "instruction": "What is world of warcraft",
#   "context": "",
#   "response": "World of warcraft is a massive online multi player role playing game. It was released in 2004 by bizarre entertainment"
# }
# ```
# 
# To load the `dolly` dataset, we use the `load_dataset()` method from the 🤗 Datasets library.

# In[5]:


from datasets import load_dataset
from random import randrange

# Load dataset from the hub
dataset = load_dataset("databricks/databricks-dolly-15k", split="train")

print(f"dataset size: {len(dataset)}")
print(dataset[randrange(len(dataset))])
# dataset size: 15011


# To instruct tune our model we need to convert our structured examples into a collection of tasks described via instructions. We define a `formatting_function` that takes a sample and returns a string with our format instruction.

# In[6]:


def format_dolly(sample):
    instruction = f"### Instruction\n{sample['instruction']}"
    context = f"### Context\n{sample['context']}" if len(sample["context"]) > 0 else None
    response = f"### Answer\n{sample['response']}"
    # join all the parts together
    prompt = "\n\n".join([i for i in [instruction, context, response] if i is not None])
    return prompt


# lets test our formatting function on a random example.

# In[7]:


from random import randrange

print(format_dolly(dataset[randrange(len(dataset))]))

# In addition, to formatting our samples we also want to pack multiple samples to one sequence to have a more efficient training. This means that we are stacking multiple samples to one sequence and split them with an EOS Token. This makes the training more efficient. Packing/stacking samples can be done during training or before. We will do it before training to save time. We created a utility method [pack_dataset](./scripts/utils/pack_dataset.py) that takes a dataset and a packing function and returns a packed dataset.
# 

# In[8]:


from transformers import AutoTokenizer

# Hugging Face model id
#model_id = "NousResearch/Llama-2-7b-hf"
model_id = "philschmid/Llama-2-7b-hf" # ungated
# model_id = "meta-llama/Llama-2-7b-hf" # gated

tokenizer = AutoTokenizer.from_pretrained(model_id)

# To pack/stack our dataset we need to first tokenize it and then we can pack it with the `pack_dataset` method. To prepare our dataset we will now: 
# 1. Format our samples using the template method and add an EOS token at the end of each sample
# 2. Tokenize our dataset to convert it from text to tokens
# 3. Pack our dataset to 2048 tokens
# 

# In[9]:


from random import randint
# add utils method to path for loading dataset
import sys
sys.path.append("./scripts/utils") # make sure you change this to the correct path 
from pack_dataset import pack_dataset


# template dataset to add prompt to each sample
def template_dataset(sample):
    sample["text"] = f"{format_dolly(sample)}{tokenizer.eos_token}"
    return sample

# apply prompt template per sample
dataset = dataset.map(template_dataset, remove_columns=list(dataset.features))
# print random sample
print(dataset[randint(0, len(dataset))]["text"])

# tokenize dataset
dataset = dataset.map(
    lambda sample: tokenizer(sample["text"]), batched=True, remove_columns=list(dataset.features)
)

# chunk dataset
lm_dataset = pack_dataset(dataset, chunk_length=2048) # We use 2048 as the maximum length for packing

# After we processed the datasets we are going save it to disk. You could also save it to S3 or the Hugging Face Hub for later use. 
# 
# _Note: Packing and preprocessing your dataset can be run outside of the Trainium instance._

# In[10]:


# save train_dataset to disk
dataset_path = "tokenized_dolly"
lm_dataset.save_to_disk(dataset_path)

# ## 3. Fine-tune Llama on AWS Trainium using the `NeuronTrainer`
# 
# Normally you would use the **[Trainer](https://huggingface.co/docs/transformers/v4.19.4/en/main_classes/trainer#transformers.Trainer)** and **[TrainingArguments](https://huggingface.co/docs/transformers/v4.19.4/en/main_classes/trainer#transformers.TrainingArguments)** to fine-tune PyTorch-based transformer models. 
# 
# But together with AWS, we have developed a `NeuronTrainer` to improve performance, robustness, and safety when training on Trainium instances. The `NeuronTrainer` is part of the `optimum-neuron` library and can be used as a 1-to-1 replacement for the `Trainer`.
# 
# When it comes to distributed training on AWS Trainium there is a few things we need to take care of. Since Llama is a big model it might not fit on a single accelerator, thats why we added support for different distributed training strategies to the `NeuronTrainer` including: 
# * [ZeRO-1](https://awsdocs-neuron.readthedocs-hosted.com/en/latest/frameworks/torch/torch-neuronx/tutorials/training/zero1_gpt2.html): shards the optimizer state over multiple devices.
# * [Tensor Parallelism](https://awsdocs-neuron.readthedocs-hosted.com/en/latest/libraries/neuronx-distributed/tensor_parallelism_overview.html): shards the model parameters along a given dimension on multiple devices, defined with `tensor_parallel_size`
# * [Sequence parallelism](https://arxiv.org/pdf/2205.05198.pdf) shards the activations on the sequence axis outside of the tensor parallel regions. It is useful because it saves memory by sharding the activations.
# * [Pipeline Parallelism](https://awsdocs-neuron.readthedocs-hosted.com/en/latest/libraries/neuronx-distributed/pipeline_parallelism_overview.html): _coming soon_
# 
# 
# We prepared a [run_clm.py](./scripts/run_clm.py), which implements those distributed training strategies for you already. If you want to more about the details you can take a look at the [documentation](https://huggingface.co/docs/optimum-neuron/guides/distributed_training). When training models on AWS Accelerators we first need to compile our model with our training arguments. 
# 
# To overcome this we added a [model cache](https://huggingface.co/docs/optimum-neuron/guides/cache_system), which allows us to use precompiled models and configuration from Hugging Face Hub to skip the compilation step. But every change in the config, will lead to a new compilation, which could result in some cache misses. 
# 
# _Note: If your configuration is not cached please open an issue on [Github](https://github.com/huggingface/optimum-neuron/issues), we are happy to include it._
# 
# We pre-compiled the config for our training already meaning you can either skip the cell below or rerun it will only take a few minutes since it reuses the cached configuration.

# In[13]:


%%bash
apt-get install apt-utils gnupg  -y

# Configure Linux for Neuron repository updates
. /etc/os-release
tee /etc/apt/sources.list.d/neuron.list > /dev/null <<EOF
deb https://apt.repos.neuron.amazonaws.com ${VERSION_CODENAME} main
EOF
wget -qO - https://apt.repos.neuron.amazonaws.com/GPG-PUB-KEY-AMAZON-AWS-NEURON.PUB | apt-key add -

# ### Set up
# 
# ---
# We begin by installing and upgrading necessary packages. Restart the kernel after executing the cell below for the first time.
# 
# ---

# In[3]:


%pip config set global.extra-index-url https://pip.repos.neuron.amazonaws.com

# In[12]:


!apt-get update -y

# In[10]:


!apt install -y aws-neuronx-dkms=2.*

# In[4]:


%%bash

# Update OS packages 
#apt-get update -y

# Install OS headers 
#apt-get install linux-headers-$(uname -r) -y

# Install git 
#apt-get install git -y

# install Neuron Driver
apt-get install aws-neuronx-dkms=2.* -y

# Install Neuron Runtime 
apt-get install aws-neuronx-collectives=2.* -y
apt-get install aws-neuronx-runtime-lib=2.* -y

# Install Neuron Tools 
apt-get install aws-neuronx-tools=2.* -y

# Add PATH
export PATH=/opt/aws/neuron/bin:$PATH

# In[5]:


%pip install -U neuronx-cc==2.* torch-neuronx torch

# In[11]:


# precompilation command 
!MALLOC_ARENA_MAX=64 neuron_parallel_compile torchrun --nproc_per_node=32 scripts/run_clm.py \
 --model_id {model_id} \
 --dataset_path {dataset_path} \
 --bf16 True \
 --learning_rate 5e-5 \
 --output_dir dolly_llama \
 --overwrite_output_dir True \
 --skip_cache_push True \
 --per_device_train_batch_size 1 \
 --gradient_checkpointing True \
 --tensor_parallel_size 8 \
 --max_steps 10 \
 --logging_steps 10 \
 --gradient_accumulation_steps 16

# _Note: Compiling without a cache can take ~40 minutes. It will also create dummy files in the `dolly_llama_sharded` during compilation you we have to remove them afterwards. We also need to add `MALLOC_ARENA_MAX=64` to limit the CPU allocation to avoid potential crashes, don't remove it for now._ 

# In[10]:


# remove dummy artifacts which are created by the precompilation command
!rm -rf dolly_llama

# After the compilation is done we can start our training with a similar command, we just need to remove the `neuron_parallel_compile`. We will use `torchrun` to launch our training script. `torchrun` is a tool that automatically distributes a PyTorch model across multiple accelerators. We can pass the number of accelerators as `nproc_per_node` arguments alongside our hyperparameters. 
# The difference to the compilation command is that we changed from `max_steps=10` to `num_train_epochs=3`.
# 
# Launch the training, with the following command.

# In[11]:


!MALLOC_ARENA_MAX=64 torchrun --nproc_per_node=32 scripts/run_clm.py \
 --model_id {model_id} \
 --dataset_path {dataset_path} \
 --bf16 True \
 --learning_rate 5e-5 \
 --output_dir dolly_llama \
 --overwrite_output_dir True \
 --per_device_train_batch_size 1 \
 --gradient_checkpointing True \
 --tensor_parallel_size 8 \
 --num_train_epochs 3 \
 --logging_steps 10 \
 --gradient_accumulation_steps 16

# Thats it, we successfully trained Llama 7B on AWS Trainium. The training took for 3 epochs on dolly (15k samples) took 43:24 minutes where the raw training time was only 31:46 minutes. This leads to a cost of ~$15.5 for the e2e training on the trn1.32xlarge instance. Not Bad! 
# 
# But before we can share and test our model we need to consolidate our model. Since we used Tensor Parallelism during training, we need to consolidate the model weights before we can use it. Tensor Parallelism shards the model weights accross different workers, only sharded checkpoints will be saved during training.
# 
# The Optimum CLI provides a way of doing that very easily via the `optimum neuron consolidate`` command:

# In[12]:


!optimum-cli neuron consolidate dolly_llama/tensor_parallel_shards dolly_llama

# Lets remove our "sharded" checkpoints as we have consolidated them already to safetensors.

# In[13]:


!rm -rf dolly_llama/tensor_parallel_shards

# ## 4. Evalaute and test fine-tuned Llama model
# 
# Similar to training to be able to run inferece on AWS Trainium or AWS Inferentia2 we need to compile our model for the correct use. We will use our Trainium instance for the inference test, but we recommend customer to switch to Inferentia2 for inference. 
# 
# Optimum Neuron implements similar to Transformers AutoModel classes for easy inference use. We will use  the `NeuronModelForCausalLM` class to load our vanilla transformers checkpoint and convert it to neuron. 

# In[14]:


from optimum.neuron import NeuronModelForCausalLM
from transformers import AutoTokenizer

compiler_args = {"num_cores": 2, "auto_cast_type": 'fp16'}
input_shapes = {"batch_size": 1, "sequence_length": 2048}

tokenizer = AutoTokenizer.from_pretrained("dolly_llama")
model = NeuronModelForCausalLM.from_pretrained(
        "dolly_llama",
        export=True,
        **compiler_args,
        **input_shapes)


# _Note: Inference compilation can take ~25minutes. Luckily, you need to only run this onces. Since you can save the model afterwards. If you are going to run on Inferentia2 you need to recompile again. The compilation is parameter and hardware specific._

# In[ ]:


# COMMENT IN if you want to save the compiled model
# model.save_pretrained("compiled_dolly_llama")

# We can now test inference, but have to make sure we format our input to our prompt format we used for fine-tuning. Therefore we created a helper method, which accepts a `dict` with our `instruction` and optionally a `context`. 

# In[ ]:


def format_dolly_infernece(sample):
    instruction = f"### Instruction\n{sample['instruction']}"
    context = f"### Context\n{sample['context']}" if "context" in sample else None
    response = f"### Answer\n"
    # join all the parts together
    prompt = "\n\n".join([i for i in [instruction, context, response] if i is not None])
    return prompt


def generate(sample): 
    prompt = format_dolly_infernece(sample)
    inputs = tokenizer(prompt, return_tensors="pt")
    outputs = model.generate(**inputs,
                         max_new_tokens=512,
                         do_sample=True,
                         temperature=0.9,
                         top_k=50,
                         top_p=0.9)
    return tokenizer.decode(outputs[0], skip_special_tokens=False)[len(prompt):]

# Lets test inference. First we test without a context.
# 
# _Note: Inference is not expected to be super fast on AWS Trainium using 2 cores. For Inference we recommend using Inferentia2._

# In[ ]:


prompt = {
  "instruction": "Can you tell me something about AWS?"
}
res = generate(prompt)

print(res)

# > AWS stands for Amazon Web Services. AWS is a suite of remote computing services offered by Amazon. The most widely used of these include Amazon Elastic Compute Cloud (Amazon EC2), which provides resizable compute capacity in the cloud; Amazon Simple Storage Service (Amazon S3), which is an object storage service; and Amazon Elastic Block Store (Amazon EBS), which is designed to provide high performance, durable block storage volumes for use with AWS instances. AWS also provides other services, such as AWS Identity and Access Management (IAM), a service that enables organizations to control access to their AWS resources, and AWS Key Management Service (AWS KMS), which helps customers create and control the use of encryption keys.</s>

# That looks correct. Now, lets add some context, e.g. as you would do for RAG applications

# In[ ]:


prompt = {
  "instruction": "How can train models on AWS Trainium?",
  "context": "🤗 Optimum Neuron is the interface between the 🤗 Transformers library and AWS Accelerators including [AWS Trainium](https://aws.amazon.com/machine-learning/trainium/?nc1=h_ls) and [AWS Inferentia](https://aws.amazon.com/machine-learning/inferentia/?nc1=h_ls). It provides a set of tools enabling easy model loading, training and inference on single- and multi-Accelerator settings for different downstream tasks."
}
res = generate(prompt)

print(res)

# > You can use the Optimum Neuron interface to train models on AWS Trainium.</s> 

# Awesome, our model also correctly uses the provided context. We are done. Congrats on fine-tuning Llama on AWS Trainium.

# 
