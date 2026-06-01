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
        self.name = name
        self.side = side
        self.parent = parent

        self.start_joint = None
        self.mid_joint = None
        self.end_joint = None

        self.upper_non_roll = None
        self.lower_non_roll = None

    def create_basic_curve(self, start_joint, mid_joint, end_joint):
        pos_start_joint = cmds.xform(start_joint, q=True, ws=True, t=True)
        pos_mid_joint = cmds.xform(mid_joint, q=True, ws=True, t=True)
        pos_end_joint = cmds.xform(end_joint, q=True, ws=True, t=True)


        self.base_curve = cmds.curve(degree =1, bezier=2, p=[(pos_start_joint, pos_mid_joint, pos_end_joint)], knot=[0, 1])

        detatch_result = cmds.detachCurve("{}.u[0.5]".format(self.base_curve), ch=True, ko=True)

twist=TwistModule("arm", "L")
twist.create_basic_curve()
