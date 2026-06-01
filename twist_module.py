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
        self.shoulder_joint = self.shoulder_joint
        self.elbow_joint = self.elbow_joint
        self.wrist_joint = self.wrist_joint
        self.clavicule_joint= self.clavicule_joint

    def create_basic_curve(self):
        pos_shoulder = cmds.xform(self.shoulder_joint, q=True, ws=True, t=True)
        pos_elbow = cmds.xform(self.elbow_joint, q=True, ws=True, t=True)
        pos_wrist = cmds.xform(self.wrist_joint, q=True, ws=True, t=True)


        upper_curve = cmds.curve(degree =1, bezier=2, p=[(pos_shoulder, pos_elbow)], knot=[0, 1])
        lower_curve = cmds.curve(degree =1, bezier=2, p=[(pos_elbow, pos_wrist)], knot=[0, 1])

        detatch_result = cmds.detachCurve("{}.u[0.5]".format(base_curve), ch=True, ko=True)

twist=TwistModule("arm", "L")
twist.create_basic_curve()
