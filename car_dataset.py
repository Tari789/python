#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd


# In[7]:


car_dataset = pd.read_csv("mtcars.csv")


# In[8]:


car_dataset.head()


# In[9]:


car_dataset.columns = ['car_name','mpg','cyl','disp','hp','drat','wt','qsec','vs','am','gear','carb']
car_dataset.head()


# In[11]:


import numpy as np 
from pandas import Series, DataFrame


# In[24]:


car_group = car_dataset.groupby(car_dataset['am']) 
car_group.sum()


# In[20]:


car_dataset_subset = car_dataset [['mpg','disp']]
car_dataset_subset.head()


# In[25]:


car_group = car_dataset.groupby(car_dataset['am']) 
car_group.sum()


# In[ ]:




