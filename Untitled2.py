#!/usr/bin/env python
# coding: utf-8

# In[1]:


import numpy as np 
import pandas as pd 
from pandas import Series, DataFrame 


# In[2]:





# In[12]:


DF_obj = DataFrame({'column 1':[1,1,2,2,3,3,3,3,3,3],
                    'column 2':['a','b','c','d','d','c','c','c','c','c'],
                    'column 3':['A','A','B','B','B','C','C','C','C','C']})
DF_obj


# In[13]:


DF_obj.duplicated()


# In[15]:


DF_obj.drop_duplicates()


# In[16]:


DF_obj = DataFrame({'column 1':[1,1,2,2,3,3,3,3,3,3],
                    'column 2':['a','b','c','d','d','c','c','c','c','c'],
                    'column 3':['A','A','B','B','B','C','C','D','C','C']})
DF_obj


# In[20]:


DF_obj.drop_duplicates()


# In[21]:


DF_obj.drop_duplicates(['column 3'])


# In[ ]:




