import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import guides_module
import limbs_module
import leg_module

class TwistModule(object):  
    def __init__(self, name, side, parent=None):
        self.side = side
        self.parent = parent
        self.start_joint = None
        self.mid_joint = None
        self.end_joint = None
        self.upper_non_roll = None
        self.lower_non_roll = None
        self.shoulder_guide = shoulder_guide
        self.elbow_guide = elbow_guide
        self.wrist_guide = wrist_guide
        self.clavicule_guide= clavicule_guide

    def create_basic_curve(self):
        
