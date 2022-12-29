#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd 
import numpy as np


# In[2]:


from pandas import Series, DataFrame 


# In[10]:


missing = np.nan

series_obj = Series(['row 1','row 2','row 3','row 4','row 5', missing ,'row 6'])
series_obj


# In[11]:


series_obj.isnull()


# In[12]:


np.random.seed(25)
DF_obj = DataFrame(np.random.rand(36).reshape(6,6))
DF_obj


# In[15]:


DF_obj.loc[3:5,0] = missing
DF_obj.loc[1:4,5] = missing 
DF_obj


# In[16]:


filled_DF = DF_obj.fillna(0)
filled_DF


# In[17]:


filled_DF = DF_obj.fillna({0: 0.1, 5:1.25})
filled_DF


# In[18]:


fill_DF = DF_obj.fillna(method='ffill')
fill_DF 


# In[19]:


np.random.seed(25)
DF_obj = DataFrame(np.random.rand(36).reshape(6,6))
DF_obj.loc[3:5,0] = missing
DF_obj.loc[1:4,5] = missing 
DF_obj 


# In[20]:


DF_obj.isnull().sum() 


# In[22]:


DF_no_NaN = DF_obj.dropna()
DF_no_NaN


# In[27]:


DF_no_NaN = DF_obj.dropna(axis=1)
DF_no_NaN


# In[ ]:





# In[ ]:




