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
        #NON ROLL
        self.nonroll_upper_start = cmds.duplicate(start_joint, po=True, n=f"{self.side}_{self.name}_upperNonRollStart_JNT")[0]
        if cmds.listRelatives(self.nonroll_upper_start, parent=True):
            cmds.parent(self.nonroll_upper_start, w=True)[0]

        self.nonroll_upper_end = cmds.duplicate(mid_joint, po=True, n=f"{self.side}_{self.name}_upperNonRollEnd_JNT")[0]
        if cmds.listRelatives(self.nonroll_upper_end, parent=True):
            cmds.parent(self.nonroll_upper_end, w=True)[0]

        cmds.matchTransform(self.nonroll_upper_start, start_joint, pos=True, rot=True)
        cmds.matchTransform(self.nonroll_upper_end, mid_joint, pos=True, rot=True)
        
        cmds.parent(self.nonroll_upper_end, self.nonroll_upper_start)
        cmds.select(cl=True)
        ik_hdl_upper = cmds.ikHandle(sj=self.nonroll_upper_start, ee=self.nonroll_upper_end, sol="ikSCsolver", name=f"{self.side}_{self.name}UpperNonRollIk_HDL")[0]

        cmds.pointConstraint(start_joint, self.nonroll_upper_start, mo=False)
        cmds.pointConstraint(mid_joint, ik_hdl_upper, mo=False)



        self.nonroll_lower_start = cmds.duplicate(mid_joint, po=True, n=f"{self.side}_{self.name}_lowerNonRollStart_JNT")[0]
        if cmds.listRelatives(self.nonroll_lower_start, parent=True):
            cmds.parent(self.nonroll_lower_start, w=True)[0]

        self.nonroll_lower_end = cmds.duplicate(end_joint, po=True, n=f"{self.side}_{self.name}_lowerNonRollEnd_JNT")[0]
        if cmds.listRelatives(self.nonroll_lower_end, parent=True):
            cmds.parent(self.nonroll_lower_end, w=True)[0]

        cmds.matchTransform(self.nonroll_lower_start, mid_joint, pos=True, rot=True)
        cmds.matchTransform(self.nonroll_lower_end, end_joint, pos=True, rot=True)

        cmds.parent(self.nonroll_lower_end, self.nonroll_lower_start)
        cmds.select(cl=True)
        ik_hdl_lower = cmds.ikHandle(sj=self.nonroll_lower_start, ee=self.nonroll_lower_end, sol="ikSCsolver", name=f"{self.side}_{self.name}LowerNonRollIk_HDL")[0]

        cmds.pointConstraint(mid_joint, self.nonroll_lower_start, mo=False)
        cmds.pointConstraint(end_joint, ik_hdl_lower, mo=False)



        
        #TWIST
        self.upper_twist_start = cmds.duplicate(start_joint, po=True, n=f"{self.side}_{self.name}_upperTwistStart_JNT")[0]
        if cmds.listRelatives(self.upper_twist_start, parent=True):
            cmds.parent(self.upper_twist_start, w=True)[0]

        self.upper_twist_end = cmds.duplicate(mid_joint, po=True, n=f"{self.side}_{self.name}_upperTwistEnd_JNT")[0]
        if cmds.listRelatives(self.upper_twist_end, parent=True):
            cmds.parent(self.upper_twist_end, w=True)[0]

        cmds.matchTransform(self.upper_twist_start, start_joint, pos=True, rot=True)
        cmds.matchTransform(self.upper_twist_end, mid_joint, pos=True, rot=True)

        cmds.parent(self.upper_twist_end, self.upper_twist_start)
        cmds.select(cl=True)
        ik_hdl_upper_twist = cmds.ikHandle(sj=self.upper_twist_start, ee=self.upper_twist_end, sol="ikSCsolver", name=f"{self.side}_{self.name}UpperTwist_HDL")[0]

        cmds.parentConstraint(mid_joint, ik_hdl_upper_twist, mo=True)
        cmds.parent(self.upper_twist_start, self.nonroll_upper_start)


        
        self.lower_twist_start = cmds.duplicate(mid_joint, po=True, n=f"{self.side}_{self.name}_lowerTwistStart_JNT")[0]
        if cmds.listRelatives(self.lower_twist_start, parent=True):
            cmds.parent(self.lower_twist_start, w=True)[0]

        self.lower_twist_end = cmds.duplicate(end_joint, po=True, n=f"{self.side}_{self.name}_lowerTwistEnd_JNT")[0]
        if cmds.listRelatives(self.lower_twist_end, parent=True):
            cmds.parent(self.lower_twist_end, w=True)[0]

        cmds.matchTransform(self.lower_twist_start, mid_joint, pos=True, rot=True)
        cmds.matchTransform(self.lower_twist_end, end_joint, pos=True, rot=True)

        cmds.parent(self.lower_twist_end, self.lower_twist_start)
        cmds.select(cl=True)
        ik_hdl_lower_twist = cmds.ikHandle(sj=self.lower_twist_start, ee=self.lower_twist_end, sol="ikSCsolver", name=f"{self.side}_{self.name}LowerTwist_HDL")[0]

        cmds.parentConstraint(end_joint, ik_hdl_lower_twist, mo=True)
        cmds.parent(self.lower_twist_start, self.nonroll_lower_start)
        cmds.select(cl=True)

        return [self.nonroll_upper_start, ik_hdl_upper, ik_hdl_lower, ik_hdl_upper_twist, ik_hdl_lower_twist]
    
    def create_twist_joints(self, motion_paths_list, segment_name):

        twist_joints = []
        
        for i, mpa_node in enumerate(motion_paths_list):
            # Netegem selecció per evitar que un joint neixi com a fill de l'anterior
            cmds.select(cl=True)

            joint_name = f"{self.side}_{self.name}_{segment_name}Twist_{i}_JNT"
            sub_jnt = cmds.joint(n=joint_name)

            cmds.connectAttr(f"{mpa_node}.allCoordinates", f"{sub_jnt}.translate")
            
            cmds.connectAttr(f"{mpa_node}.rotate", f"{sub_jnt}.rotate")
            
            twist_joints.append(sub_jnt)
            
        return twist_joints
    
    def create_basic_curve(self, start_joint, mid_joint, end_joint, aim_axis="x", up_axis="y"):
        self.start_joint = start_joint
        self.mid_joint = mid_joint
        self.end_joint = end_joint

        base_twist= self.basic_twist_setup(start_joint, mid_joint, end_joint)

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

        axis_map = {"x": 0, "y": 1, "z": 2}
        aim_value = axis_map.get(aim_axis.lower(), 0)
        up_value = axis_map.get(up_axis.lower(), 1)

        vector_map = {
            "x": (1.0, 0.0, 0.0),
            "y": (0.0, 1.0, 0.0),
            "z": (0.0, 0.0, 1.0)
        }
        up_vector = vector_map.get(up_axis.lower(), (0.0, 1.0, 0.0))

        self.upper_motion_paths = []
        self.lower_motion_paths = []
        self.upper_twist_joints = []
        self.lower_twist_joints = []

        for crv in [self.upper_curve, self.lower_curve]:
            
            crv_shape = cmds.listRelatives(crv, shapes=True)[0]
            
            if crv == self.upper_curve:
                segment_name = "upper"
                target_jnt_list = self.upper_twist_joints
                target_list = self.upper_motion_paths
                non_roll_object = self.nonroll_upper_start
                
            else:
                segment_name = "lower"
                target_jnt_list = self.lower_twist_joints
                target_list = self.lower_motion_paths
                non_roll_object = self.nonroll_lower_start

            for i in range(5):
                motion_path = NodeCreator(side=self.side, node_type="motionPath", base_name=self.name, name=segment_name, tag="segment", parent=None, custom_suffix="MPA")
                motion_path_node = motion_path.create()
                cmds.connectAttr(f"{crv_shape}.worldSpace[0]", f"{motion_path_node}.geometryPath")
                cmds.setAttr(f"{motion_path_node}.fractionMode", True)

                cmds.setAttr(f"{motion_path_node}.follow", True)

                cmds.setAttr(f"{motion_path_node}.frontAxis", aim_value)
                cmds.setAttr(f"{motion_path_node}.upAxis", up_value)

                cmds.setAttr(f"{motion_path_node}.worldUpType", 2)
                cmds.setAttr(f"{motion_path_node}.worldUpVector", up_vector[0], up_vector[1], up_vector[2])

                cmds.connectAttr(f"{non_roll_object}.worldMatrix[0]", f"{motion_path_node}.worldUpMatrix")

                u_value = 0.01 + ((i / 4.0) * 0.98)
                cmds.setAttr(f"{motion_path_node}.uValue", u_value)

                target_list.append(motion_path_node)

                mdl_path = NodeCreator(side=self.side, node_type="multDoubleLinear", base_name=self.name, name=segment_name, tag="segment", parent=None, custom_suffix="MDL")
                mdl_node = mdl_path.create()

                cmds.setAttr(f"{mdl_node}.input1", 30.0)
                
                cmds.setAttr(f"{mdl_node}.input2", u_value)
                cmds.connectAttr(f"{mdl_node}.output", f"{motion_path_node}.frontTwist")

            
            print(f"La curva de {segment_name} funciona perfectamente hasta aquí.")
        self.upper_twist_joints = self.create_twist_joints(self.upper_motion_paths, "upper")
        self.lower_twist_joints = self.create_twist_joints(self.lower_motion_paths, "lower")

        return [f"{self.side}_{self.name}BaseDriver_CRV"] + base_twist
