#!/usr/bin/env python
# coding: utf-8

# In[1]:


import numpy as np 
import pandas as pd 
from pandas import Series, DataFrame 


# In[3]:


DF_obj = pd.DataFrame(np.arange(36).reshape(6,6))
DF_obj


# In[4]:


DF_obj_2 = pd.DataFrame(np.arange(15).reshape(5,3))
DF_obj_2


# In[5]:


pd.concat([DF_obj,DF_obj_2], axis=1)


# In[6]:


pd.concat([DF_obj,DF_obj_2])


# In[7]:


DF_obj.drop([0,2])


# In[8]:


DF_obj.drop([0,2], axis=1)


# In[9]:


series_obj = Series(np.arange(6))
series_obj.name = "added_variable"
series_obj 


# In[10]:


variable_added = DataFrame.join(DF_obj, series_obj)
variable_added


# In[13]:


added_datatable = variable_added.append(variable_added, ignore_index=False)
added_datatable


# In[14]:


added_datatable = variable_added.append(variable_added, ignore_index=True)
added_datatable


# In[16]:


DF_obj = pd.DataFrame(np.arange(36).reshape(6,6))
DF_obj


# In[18]:


DF_sorted = DF_obj.sort_values(by=(5), ascending=[False]) 
DF_sorted


# In[ ]:




