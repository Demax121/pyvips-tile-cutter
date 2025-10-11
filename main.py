import os
vipshome = 'libvips\\bin'
os.environ['PATH'] = vipshome + ';' + os.environ['PATH']
import pyvips


# ONLY ADD CODE BELOWE THIS COMMENT