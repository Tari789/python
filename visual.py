#!/usr/bin/env python
# coding: utf-8

# In[2]:


import numpy as np
from numpy.random import randn
import pandas as pd 
from pandas import Series, DataFrame 

import matplotlib.pyplot as plt 
from matplotlib import rcParams 


# In[3]:


x = range(1,10)
y = [1,2,3,4,0,4,3,2,1] 

plt.plot(x,y)


# In[4]:


car_dataset = pd.read_csv("mtcars.csv")
car_dataset.columns = ['car_name','mpg','cyl','disp','hp','drat','wt','qsec','vs','am','gear','carb']

mpg = car_dataset['mpg']


# In[5]:


mpg.plot()


# In[6]:


df = car_dataset[['cyl','wt','mpg']]
df.plot()


# In[7]:


###bar 


# In[8]:


plt.bar(x,y)


# In[9]:


mpg.plot(kind='bar')


# In[10]:


mpg.plot(kind='barh')


# In[12]:


x = [1,2,3,4,0.5]
plt.pie(x)
plt.show


# In[14]:


plt.pie(x)
plt.savefig('pie_chart.png')
plt.show()


# In[15]:


get_ipython().run_line_magic('pwd', '')


# In[ ]:




