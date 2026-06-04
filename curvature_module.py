import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import guides_module
import limbs_module
import leg_module
import rigRoot_module
from nodeCreator_module import NodeCreator

class CurvatureModule(object):  
    def __init__(self, name, side, parent=None, root_instance = None):
        self.name = name
        self.side = side
        self.parent = parent
        self.root_instance = root_instance

        self.start_joint = None
        self.mid_joint = None
        self.end_joint = None

        self.base_curve = None

    
    def create_curve(self, start_joint, mid_joint, end_joint):
        
        self.start_joint = start_joint
        self.mid_joint = mid_joint
        self.end_joint = end_joint
        
        pos_start_joint = cmds.xform(start_joint, q=True, ws=True, t=True)
        pos_mid_joint = cmds.xform(mid_joint, q=True, ws=True, t=True)
        pos_end_joint = cmds.xform(end_joint, q=True, ws=True, t=True)
        
        self.base_curve = cmds.curve(degree=1, p=[pos_start_joint, pos_mid_joint, pos_end_joint])