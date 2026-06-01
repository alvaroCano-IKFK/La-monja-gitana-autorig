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

        self.base_curve = None
        self.upper_curve = None
        self.lower_curve = None

    def create_basic_curve(self, start_joint, mid_joint, end_joint):
        self.start_joint = start_joint
        self.mid_joint = mid_joint
        self.end_joint = end_joint

        pos_start_joint = cmds.xform(start_joint, q=True, ws=True, t=True)
        pos_mid_joint = cmds.xform(mid_joint, q=True, ws=True, t=True)
        pos_end_joint = cmds.xform(end_joint, q=True, ws=True, t=True)


        self.base_curve = cmds.curve(degree =1, bezier=2, p=[(pos_start_joint, pos_mid_joint, pos_end_joint)], knot=[0, 1])

        detatch_result = cmds.detachCurve((f"{self.base_curve}.u[0.5]"), ch=True, ko=True)

        self.upper_curve = cmds.rename(detatch_result[0], f"{self.name}UpperSegment_CRV")
        self.lower_curve = cmds.rename(detatch_result[1], f"{self.name}LowerSegment_CRV")

        history = cmds.listHistory(self.upper_curve)
        node_detach = cmds.ls(history, type="detachCurve")[0]
        cmds.setAttr(f"{node_detach}.parameter[0]", 0.5)

        cmds.rename(self.base_curve, f"{self.side}_{self.name}BaseDriver_CRV")

        print(f"[Twist {self.name.upper()}] Sistema de curvas creado con éxito para {start_joint}.")

create_twist_module = partial(TwistModule, name="ArmTwist", side="L")


