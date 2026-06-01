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

        self.nonroll_upper_start = None
        self.nonroll_upper_end = None
        self.nonroll_lower_start = None
        self.nonroll_lower_end = None
        self.upper_twist_start = None
        self.upper_twist_end = None
        self.lower_twist_start = None
        self.lower_twist_end = None

        self.upper_motion_paths = []
        self.lower_motion_paths = []

    def basic_twist_setup(self, start_joint, mid_joint, end_joint):
        self.nonroll_upper_start = cmds.duplicate(start_joint, po=True, n=f"{self.side}_{self.name}_upperNonRoll_JNT")[0]
        self.nonroll_upper_end = cmds.duplicate(mid_joint, po=True, n=f"{self.side}_{self.name}_lowerNonRoll_JNT")[0]
        cmds.parent(self.nonroll_lower_joints,self.nonroll_upper_joints)

        ik_hdl_upper = cmds.ikHandle(sj=self.nonroll_upper_start, ee=self.nonroll_upper_end, sol="ikRPsolver", name=f"{self.side}_{self.name}_upperNonRoll_IKH")[0]

        cmds.pointConstraint(self.nonroll_upper_start, start_joint, mo=False)
        cmds.pointConstraint(self.nonroll_upper_end, mid_joint, mo=False)

        self.nonroll_lower_start = cmds.duplicate(mid_joint, po=True, n=f"{self.side}_{self.name}_lowerNonRoll_JNT")[0]
        self.nonroll_lower_end = cmds.duplicate(end_joint, po=True, n=f"{self.side}_{self.name}_lowerNonRoll_JNT")[0]
        cmds.parent(self.nonroll_lower_joints,self.nonroll_upper_joints)

        ik_hdl_lower = cmds.ikHandle(sj=self.nonroll_lower_start, ee=self.nonroll_lower_end, sol="ikRPsolver", name=f"{self.side}_{self.name}_lowerNonRoll_IKH")[0]

        cmds.pointConstraint(self.nonroll_lower_start, mid_joint, mo=False)
        cmds.pointConstraint(self.nonroll_lower_end, end_joint, mo=False)
        
        self.upper_twist_start = cmds.duplicate(start_joint, po=True, n=f"{self.side}_{self.name}_upperTwist_JNT")[0]
        self.upper_twist_end = cmds.duplicate(mid_joint, po=True, n=f"{self.side}_{self.name}_upperTwist_JNT")[0]
        cmds.parent(self.upper_twist_end, self.upper_twist_start)
        cmds.parent(self.upper_twist_joints,self.nonroll_upper_joints)

        ik_hdl_upper_twist = cmds.ikHandle(sj=self.upper_twist_start, ee=self.upper_twist_end, sol="ikRPsolver", name=f"{self.side}_{self.name}_upperTwist_IKH")[0]
        cmds.parent =(self.mid_joint, self.ik_hdl_upper_twist)


        self.lower_twist_start = cmds.duplicate(mid_joint, po=True, n=f"{self.side}_{self.name}_lowerTwist_JNT")[0]
        self.lower_twist_end = cmds.duplicate(end_joint, po=True, n=f"{self.side}_{self.name}_lowerTwist_JNT")[0]
        cmds.parent(self.lower_twist_end, self.lower_twist_start)
        cmds.parent(self.lower_twist_joints,self.nonroll_upper_joints)

        ik_hdl_lower_twist = cmds.ikHandle(sj=self.lower_twist_start, ee=self.lower_twist_end, sol="ikRPsolver", name=f"{self.side}_{self.name}_lowerTwist_IKH")[0]
        cmds.parent =(self.end_joint, self.ik_hdl_lower_twist)


    def create_basic_curve(self, start_joint, mid_joint, end_joint):
        self.start_joint = start_joint
        self.mid_joint = mid_joint
        self.end_joint = end_joint

        pos_start_joint = cmds.xform(start_joint, q=True, ws=True, t=True)
        pos_mid_joint = cmds.xform(mid_joint, q=True, ws=True, t=True)
        pos_end_joint = cmds.xform(end_joint, q=True, ws=True, t=True)


        self.base_curve = cmds.curve(degree =1, p=[pos_start_joint, pos_mid_joint, pos_end_joint])

        detatch_result = cmds.detachCurve((f"{self.base_curve}.u[1.0]"), ch=True, k=[True, True])

        self.upper_curve = cmds.rename(detatch_result[0], f"{self.side}_{self.name}UpperSegment_CRV")
        self.lower_curve = cmds.rename(detatch_result[1], f"{self.side}_{self.name}LowerSegment_CRV")

        history = cmds.listHistory(self.upper_curve)
        node_detach = cmds.ls(history, type="detachCurve")[0]
        cmds.setAttr(f"{node_detach}.parameter[0]", 1.0)

        cmds.rename(self.base_curve, f"{self.side}_{self.name}BaseDriver_CRV")

        for crv in [self.upper_curve, self.lower_curve]:
            
            crv_shape = cmds.listRelatives(crv, shapes=True)[0]
            
            if crv == self.upper_curve:
                segment_name = "upper"
                target_list = self.upper_motion_paths
            else:
                segment_name = "lower"
                target_list = self.lower_motion_paths

            for i in range(5):
                motion_path = NodeCreator(side=self.side, node_type="motionPath", base_name=self.name, name=segment_name, tag="segment", parent=None, custom_suffix="MPA")
                motion_path_node = motion_path.create()
                cmds.connectAttr(f"{crv_shape}.worldSpace[0]", f"{motion_path_node}.geometryPath")
                cmds.setAttr(f"{motion_path_node}.fractionMode", True)

                u_value = 0.01 + ((i / 4.0) * 0.98)
                cmds.setAttr(f"{motion_path_node}.uValue", u_value)

                target_list.append(motion_path_node)

            print(f"La curva de {segment_name} funciona perfectamente hasta aquí.")
