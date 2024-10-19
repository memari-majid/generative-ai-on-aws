#!/usr/bin/env python
# coding: utf-8

# ## Using Huggingface DLC to Host the Whisper Model for Automatic Speech Recognition Tasks
# 
# This notebook is derived from this blog post:  https://aws.amazon.com/blogs/machine-learning/host-the-whisper-model-on-amazon-sagemaker-exploring-inference-options/
# 
# This notebook requires the **ml.m5.large** instance with **Data Science 2.0** kernel (Python 3.8).

# #### Common set up 

# In[ ]:


# Install required packages
# %pip install -U openai-whisper==20231117
# %pip install -U torchaudio==2.1.2
# %pip install -U datasets==2.16.1
# %pip install -U librosa==0.10.1
# %pip install -U soundfile==0.12.1
# %pip install -U transformers==4.28.1 -q
# %pip install -U accelerate==0.20.3 -q
#%conda install -y ffmpeg

# In[4]:


import torch
import whisper
import torchaudio
import sagemaker
import time
import boto3

# In[13]:


# basic configurations 
sess = sagemaker.session.Session()
bucket = sess.default_bucket()
region = sess._region_name
prefix = 'whisper'
role = sagemaker.get_execution_role()

# below boto3 clients are for invoking asynchronous endpoint 
sm_runtime = boto3.client("sagemaker-runtime")

# ### Create Whisper Hugging Face model artifacts and upload to S3 bucket

# In[6]:


!mkdir -p model

# In[7]:


from transformers import WhisperProcessor, AutoModelForSpeechSeq2Seq

# Load the pre-trained model
model_name = "openai/whisper-base"
model = AutoModelForSpeechSeq2Seq.from_pretrained(model_name)

# Define a directory where you want to save the model
save_directory = "./model"

# Save the model to the specified directory
model.save_pretrained(save_directory)

from transformers import WhisperTokenizer

tokenizer = WhisperTokenizer.from_pretrained(model_name)
tokenizer.save_pretrained(save_directory)
processor = WhisperProcessor.from_pretrained(model_name)
processor.save_pretrained(save_directory)

# In[8]:


!tar cvzf model.tar.gz -C model/ .

model_uri = sess.upload_data('model.tar.gz', bucket = bucket, key_prefix=f"{prefix}/huggingface/model")
!rm model.tar.gz
!rm -rf model
model_uri

# In[14]:


# Generate a unique model name and provide image uri

id = int(time.time())
model_name = f'whisper-hf-model-{id}'

# !Please change the image URI for the region that you are using:e.g. us-east-1
image = f"763104351884.dkr.ecr.{region}.amazonaws.com/huggingface-pytorch-inference:2.0.0-transformers4.28.1-gpu-py310-cu118-ubuntu20.04"

# In[15]:


# Create a HuggingFaceModel for deployment
from sagemaker.huggingface.model import HuggingFaceModel

whisper_hf_model = HuggingFaceModel(
    model_data=model_uri,
    role=role, 
    image_uri = image,
    entry_point="inference.py",
    source_dir='code_huggingface',
    name=model_name,
    env = {
        "chunk_length_s":"30",
        'MMS_MAX_REQUEST_SIZE': '2000000000',
        'MMS_MAX_RESPONSE_SIZE': '2000000000',
        'MMS_DEFAULT_RESPONSE_TIMEOUT': '900'
    }
)

# ### Real-time inference 

# In[16]:


from sagemaker.serializers import DataSerializer
from sagemaker.deserializers import JSONDeserializer

# Define serializers and deserializer
audio_serializer = DataSerializer(content_type="audio/x-audio")
deserializer = JSONDeserializer()

# In[17]:


# Deploy the model for real-time inference
endpoint_name = f'whisper-hf-real-time-endpoint-{id}'

real_time_predictor = whisper_hf_model.deploy(
    initial_instance_count=1,
    instance_type="ml.g4dn.xlarge",
    endpoint_name = endpoint_name,
    serializer=audio_serializer,
    deserializer = deserializer
    )

# In[ ]:


%mkdir -p tmp/

# In[18]:


# Download a test data sample from huggingface dataset
import soundfile as sf
from datasets import load_dataset
dataset = load_dataset('MLCommons/peoples_speech', split='train', streaming = True)
sample = next(iter(dataset))
audio_data = sample['audio']['array']
output_path = 'tmp/sample_audio.wav'
sf.write(output_path, audio_data, sample['audio']['sampling_rate'])

print(f"Audio sample saved to '{output_path}'.")

# In[19]:


import json

# Perform real-time inference
audio_path = "tmp/sample_audio.wav"
#audio_path = "wav/starwars_3s.wav" 
#audio_path = "wav/starwars_10s.wav"

response = real_time_predictor.predict(data=audio_path)

print(response[0])

# ### Cleanup

# In[ ]:


# # optional: Delete real-time inference endpoint, this is not required for below steps
# real_time_predictor.delete_endpoint()

# In[ ]:




# ### Batch Transform Inference

# In[ ]:


# # Create a transformer
# whisper_transformer = whisper_hf_model.transformer(
#     instance_count = 1,
#     instance_type = "ml.g4dn.xlarge",
#     output_path="s3://{}/{}/batch-transform/".format(bucket, prefix),
#     max_payload = 100
# )

# In[ ]:


# # Please provide the S3 path where you have one or more audio files that you want to process 
# data = "s3://xxx/audio-files/"

# In[ ]:


# # Define request data and job name
# job_name = f"whisper-hf-batch-transform-{id}"

# # Start batch transform job
# whisper_transformer.transform(data = data, job_name= job_name, wait = False)

# ### Asynchronous Inference 

# In[ ]:


# %%time
# from sagemaker.async_inference import AsyncInferenceConfig

# # Create an AsyncInferenceConfig object
# async_config = AsyncInferenceConfig(
#     output_path=f"s3://{bucket}/{prefix}/output", 
#     max_concurrent_invocations_per_instance = 4,
#     # notification_config = {
#             #   "SuccessTopic": "arn:aws:sns:us-east-2:123456789012:MyTopic",
#             #   "ErrorTopic": "arn:aws:sns:us-east-2:123456789012:MyTopic",
#     # }, #  Notification configuration 
# )

# # Deploy the model for async inference
# endpoint_name = f'whisper-hf-async-endpoint-{id}'
# async_predictor = whisper_hf_model.deploy(
#     async_inference_config=async_config,
#     initial_instance_count=1, # number of instances
#     instance_type ='ml.g4dn.xlarge', # instance type
#     endpoint_name = endpoint_name
# )

# In[ ]:


# # Provide the S3 path for the audio file you want to processs
# input_path = "s3://xxx/audio-files/xxx.mp3"

# In[ ]:


# # Perform async inference
# initial_args = {'ContentType':"audio/x-audio"}
# response = async_predictor.predict_async(initial_args = initial_args, input_path=input_path)
# response.output_path

# In[ ]:




# ### Optional: Test autoscaling configurations for Async inference 

# In[ ]:


# autoscale = boto3.client('application-autoscaling') 
# resource_id='endpoint/' + endpoint_name + '/variant/' + 'AllTraffic'

# # Register scalable target
# register_response = autoscale.register_scalable_target(
#     ServiceNamespace='sagemaker', 
#     ResourceId=resource_id,
#     ScalableDimension='sagemaker:variant:DesiredInstanceCount',
#     MinCapacity=0,  
#     MaxCapacity=3 # * check how many instances available in your account
# )

# # Define scaling policy
# scalingPolicy_response = autoscale.put_scaling_policy(
#     PolicyName='Invocations-ScalingPolicy',
#     ServiceNamespace='sagemaker', # The namespace of the AWS service that provides the resource. 
#     ResourceId=resource_id,  
#     ScalableDimension='sagemaker:variant:DesiredInstanceCount', # SageMaker supports only Instance Count
#     PolicyType='TargetTrackingScaling', # 'StepScaling'|'TargetTrackingScaling'
#     TargetTrackingScalingPolicyConfiguration={
#         'TargetValue': 3.0, # The target value for the metric. 
#         'CustomizedMetricSpecification': {
#             'MetricName': 'ApproximateBacklogSizePerInstance',
#             'Namespace': 'AWS/SageMaker',
#             'Dimensions': [
#                 {'Name': 'EndpointName', 'Value': endpoint_name }
#             ],
#             'Statistic': 'Average',
#         },
#         'ScaleInCooldown': 60, # The cooldown period helps you prevent your Auto Scaling group from launching or terminating 
#                                 # additional instances before the effects of previous activities are visible. 
#                                 # You can configure the length of time based on your instance startup time or other application needs.
#                                 # ScaleInCooldown - The amount of time, in seconds, after a scale in activity completes before another scale in activity can start. 
#         'ScaleOutCooldown': 60 # ScaleOutCooldown - The amount of time, in seconds, after a scale out activity completes before another scale out activity can start.
        
#         # 'DisableScaleIn': True|False - indicates whether scale in by the target tracking policy is disabled. 
#                             # If the value is true , scale in is disabled and the target tracking policy won't remove capacity from the scalable resource.
#     }
# )

# scalingPolicy_response

# In[ ]:


# # Trigger 1000 asynchronous invocations with autoscaling from 1 to 3
# # then scale down to 0 on completion

# print(endpoint_name)
# for i in range(1,1000):
#     response = sm_runtime.invoke_endpoint_async(
#     EndpointName=endpoint_name, 
#     InputLocation=input_path)
    
# print("\nAsync invocations for Hugging Face model serving with autoscaling\n")

# ### Clean up

# In[ ]:


# # Delete Asynchronous inference endpoint
# async_predictor.delete_endpoint()

# In[ ]:


