import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import guides_module
import limbs_module
import leg_module
from nodeCreator_module import NodeCreator

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

        self.upper_motion_paths = []
        self.lower_motion_paths = []

    def create_basic_curve(self, start_joint, mid_joint, end_joint):
        self.start_joint = start_joint
        self.mid_joint = mid_joint
        self.end_joint = end_joint

        pos_start_joint = cmds.xform(start_joint, q=True, ws=True, t=True)
        pos_mid_joint = cmds.xform(mid_joint, q=True, ws=True, t=True)
        pos_end_joint = cmds.xform(end_joint, q=True, ws=True, t=True)


        self.base_curve = cmds.curve(degree =2, p=[pos_start_joint, pos_mid_joint, pos_end_joint], knot=[0, 1, 2, 2])

        detatch_result = cmds.detachCurve((f"{self.base_curve}.u[0.5]"), ch=True, k=[True, True])

        self.upper_curve = cmds.rename(detatch_result[0], f"{self.side}_{self.name}UpperSegment_CRV")
        self.lower_curve = cmds.rename(detatch_result[1], f"{self.side}_{self.name}LowerSegment_CRV")

        history = cmds.listHistory(self.upper_curve)
        node_detach = cmds.ls(history, type="detachCurve")[0]
        cmds.setAttr(f"{node_detach}.parameter[0]", 0.5)

        cmds.rename(self.base_curve, f"{self.side}_{self.name}BaseDriver_CRV")

        for crv in [self.upper_curve, self.lower_curve]:
            
            crv_shape = cmds.listRelatives(crv, shapes=True)[0]
            
            if crv == self.upper_curve:
                segment_name = "Upper"
                target_list = self.upper_motion_paths
            else:
                segment_name = "Lower"
                target_list = self.lower_motion_paths

            for i in range(5):
                motion_path = NodeCreator(side=self.side, node_type="motionPath", base_name=self.name, name=segment_name, tag=None, parent=None, custom_suffix="MPA")
                motion_path_node = motion_path.create()
                cmds.connectAttr(f"{crv_shape}.worldSpace[0]", f"{motion_path_node}.geometryPath")
                cmds.setAttr(f"{motion_path_node}.fractionMode", True)
                target_list.append(motion_path_node)

            print(f"La curva de {segment_name} funciona perfectamente hasta aquí.")
