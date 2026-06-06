import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import guides_module
import limbs_module
import leg_module
#import rigRoot_module
import curvature_module
from nodeCreator_module import NodeCreator

class TwistModule(object):  
    def __init__(self, name, side, parent=None, root_instance = None):
        self.name = name
        self.side = side
        self.parent = parent
        self.root_instance = root_instance

        self.start_joint = None
        self.mid_joint = None
        self.end_joint = None

        self.base_curve = None
        self.upper_curve = None
        self.lower_curve = None

        self.nonroll_upper_start = None
        self.nonroll_upper_end = None
        
        self.upper_twist_start = None
        self.upper_twist_end = None
        self.lower_twist_start = None
        self.lower_twist_end = None

        self.upper_motion_paths = []
        self.lower_motion_paths = []

    def basic_twist_setup(self, start_joint, mid_joint, end_joint):
        # NON ROLL
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
        cmds.pointConstraint(start_joint, self.nonroll_upper_start)

        ik_hdl_upper = cmds.ikHandle(sj=self.nonroll_upper_start, ee=self.nonroll_upper_end, sol="ikSCsolver", name=f"{self.side}_{self.name}UpperNonRollIk_HDL")[0]
        cmds.pointConstraint(mid_joint, ik_hdl_upper, mo=False)

        # TWIST
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
        cmds.parent(self.lower_twist_start, mid_joint)

        self.lower_twist_end = cmds.duplicate(end_joint, po=True, n=f"{self.side}_{self.name}_lowerTwistEnd_JNT")[0]
        if cmds.listRelatives(self.lower_twist_end, parent=True):
            cmds.parent(self.lower_twist_end, w=True)[0]

        cmds.matchTransform(self.lower_twist_start, mid_joint, pos=True, rot=True)
        cmds.matchTransform(self.lower_twist_end, end_joint, pos=True, rot=True)

        cmds.parent(self.lower_twist_end, self.lower_twist_start)
        cmds.select(cl=True)
        ik_hdl_lower_twist = cmds.ikHandle(sj=self.lower_twist_start, ee=self.lower_twist_end, sol="ikSCsolver", name=f"{self.side}_{self.name}LowerTwist_HDL")[0]

        cmds.parentConstraint(end_joint, ik_hdl_lower_twist, mo=True)

        return [self.nonroll_upper_start, ik_hdl_upper, ik_hdl_upper_twist, ik_hdl_lower_twist]
    
    def create_twist_joints(self, motion_paths_list, segment_name):
        twist_joints = []
        for i, mpa_node in enumerate(motion_paths_list):
            cmds.select(cl=True)
            joint_name = f"{self.side}_{self.name}_{segment_name}Twist_0{i+1}_JNT"
            twist_jnt = cmds.joint(n=joint_name)

            cmds.connectAttr(f"{mpa_node}.allCoordinates", f"{twist_jnt}.translate")
            cmds.connectAttr(f"{mpa_node}.rotate", f"{twist_jnt}.rotate")
            
            twist_joints.append(twist_jnt)

        return twist_joints
    
    def create_basic_curve(self, start_joint, mid_joint, end_joint,
                        aim_axis="x", up_axis="y",
                        front_axis_idx=None, up_axis_idx=None,
                        source_curve=None):   # ← parámetros nuevos
        
        self.start_joint = start_joint
        self.mid_joint   = mid_joint
        self.end_joint   = end_joint

        base_twist = self.basic_twist_setup(start_joint, mid_joint, end_joint)

        # ==============================================================
        # CURVAS DE SEGMENTO
        # ==============================================================
        if source_curve and cmds.objExists(source_curve):
            # Usamos la degree2_curve del CurvatureModule directamente.
            # NO se duplica — el detach se hace sobre ella misma.
            self.base_curve = source_curve
            print(f"[TwistModule] Usando degree2_curve de CurvatureModule: '{source_curve}'")
        else:
            # Fallback: crea una curva propia
            pos_start = cmds.xform(start_joint, q=True, ws=True, t=True)
            pos_mid   = cmds.xform(mid_joint,   q=True, ws=True, t=True)
            pos_end   = cmds.xform(end_joint,   q=True, ws=True, t=True)
            self.base_curve = cmds.curve(
                degree=2, p=[pos_start, pos_mid, pos_end],
                name=f"{self.side}_{self.name}BaseDriver_CRV"
            )
            print(f"[TwistModule] Curva base creada internamente (fallback).")

        # El detach SIEMPRE se hace aquí sobre self.base_curve
        detach_result = cmds.detachCurve(
            f"{self.base_curve}.u[0.5]",
            ch=True,
            k=[True, True],
            rpo=False   # keepOriginal=True, no destruye la degree2_curve
        )
        self.upper_curve = cmds.rename(detach_result[0],
                                    f"{self.side}_{self.name}UpperSegment_CRV")
        self.lower_curve = cmds.rename(detach_result[1],
                                    f"{self.side}_{self.name}LowerSegment_CRV")

        history     = cmds.listHistory(self.upper_curve)
        detach_node = cmds.ls(history, type="detachCurve")[0]
        cmds.setAttr(f"{detach_node}.parameter[0]", 0.5)
            

        cmds.rename(self.base_curve, f"{self.side}_{self.name}BaseDriver_CRV")

        axis_map = {"x": 0, "y": 1, "z": 2, "xneg": 0, "yneg": 1, "zneg": 2}
            
        if front_axis_idx is None:
            front_axis_idx = axis_map.get(aim_axis.lower(), 0)
        if up_axis_idx is None:
            up_axis_idx = axis_map.get(up_axis.replace("neg","").lower(), 1)

        vector_map = {
                "x": (1.0, 0.0, 0.0),
                "y": (0.0, 1.0, 0.0),
                "z": (0.0, 0.0, 1.0),
                "xneg": (-1.0,  0.0,  0.0),
                "yneg": ( 0.0, -1.0,  0.0),
                "zneg": ( 0.0,  0.0, -1.0),
            }
            
            # El vector se obtiene de forma pura según lo que dictaminó el módulo padre
        up_vector = vector_map.get(up_axis.lower(), (0.0, 1.0, 0.0))

        self.upper_motion_paths = []
        self.lower_motion_paths = []
        self.upper_twist_joints = []
        self.lower_twist_joints = []

        for crv in [self.upper_curve, self.lower_curve]:
            crv_shape = cmds.listRelatives(crv, shapes=True)[0]
                
            if crv == self.upper_curve:
                segment_name = "upper"
                target_list = self.upper_motion_paths
                twist_start_joint = self.upper_twist_start
            else:
                segment_name = "lower"
                target_list = self.lower_motion_paths
                twist_start_joint = self.lower_twist_start

            if segment_name == "upper":
                pma_twist = NodeCreator(
                        side=self.side, node_type="plusMinusAverage",
                        base_name=self.name, name=segment_name,
                        tag="twistExtract", parent=None, custom_suffix=None
                    )
                pma_node = pma_twist.create()
                cmds.setAttr(f"{pma_node}.operation", 2)  # Subtract

                cmds.connectAttr(f"{twist_start_joint}.rotateX", f"{pma_node}.input1D[0]")
                cmds.connectAttr(f"{self.nonroll_upper_start}.rotateX", f"{pma_node}.input1D[1]")

                twist_source = f"{pma_node}.output1D"
            else:
                twist_source = f"{twist_start_joint}.rotateX"

            # Inversión matemática del valor de rotación frontTwist para comportamiento de espejo en R
            if self.side == "R":
                md_mirror = NodeCreator(
                        side=self.side, node_type="multiplyDivide", 
                        base_name=self.name, name=f"{segment_name}Mirror", 
                        tag="invert", parent=None, custom_suffix="MDN"
                    )
                md_mirror_node = md_mirror.create()
                cmds.connectAttr(twist_source, f"{md_mirror_node}.input1X")
                cmds.setAttr(f"{md_mirror_node}.input2X", -1.0)
                final_twist_source = f"{md_mirror_node}.outputX"
            else:
                final_twist_source = twist_source

            md_path = NodeCreator(side=self.side, node_type="multiplyDivide", base_name=self.name, name=segment_name, tag="segment", parent=None, custom_suffix="MDN")
            md_node = md_path.create()

            cmds.connectAttr(final_twist_source, f"{md_node}.input1X")
            cmds.connectAttr(final_twist_source, f"{md_node}.input1Y")
            cmds.connectAttr(final_twist_source, f"{md_node}.input1Z")

            for i in range(5):
                motion_path = NodeCreator(side=self.side, node_type="motionPath", base_name=self.name, name=segment_name, tag="segment", parent=None, custom_suffix="MPA")
                motion_path_node = motion_path.create()
                cmds.connectAttr(f"{crv_shape}.worldSpace[0]", f"{motion_path_node}.geometryPath")
                    
                cmds.setAttr(f"{motion_path_node}.fractionMode", True)
                cmds.setAttr(f"{motion_path_node}.follow", True)

                cmds.setAttr(f"{motion_path_node}.frontAxis", front_axis_idx)
                cmds.setAttr(f"{motion_path_node}.upAxis", up_axis_idx)

                    # Método estable usando el vector calculado
                cmds.setAttr(f"{motion_path_node}.worldUpType", 2)
                cmds.setAttr(f"{motion_path_node}.worldUpVector", up_vector[0], up_vector[1], up_vector[2])
                    
                if self.side == "R":
                    cmds.setAttr(f"{motion_path_node}.inverseUp", 1)
                    cmds.setAttr(f"{motion_path_node}.inverseFront", 1)

                u_value = 0.01 + ((i / 4.0) * 0.98)
                cmds.setAttr(f"{motion_path_node}.uValue", u_value)

                target_list.append(motion_path_node)

                if i == 0:
                    pass
                elif i == 4:
                    cmds.connectAttr(final_twist_source, f"{motion_path_node}.frontTwist")
                elif i == 1:    
                    cmds.setAttr(f"{md_node}.input2X", u_value)
                    cmds.connectAttr(f"{md_node}.outputX", f"{motion_path_node}.frontTwist")
                elif i == 2:  
                    cmds.setAttr(f"{md_node}.input2Y", u_value)
                    cmds.connectAttr(f"{md_node}.outputY", f"{motion_path_node}.frontTwist")
                elif i == 3:  
                    cmds.setAttr(f"{md_node}.input2Z", u_value)
                    cmds.connectAttr(f"{md_node}.outputZ", f"{motion_path_node}.frontTwist")

                
        self.upper_twist_joints = self.create_twist_joints(self.upper_motion_paths, "upper")
        self.lower_twist_joints = self.create_twist_joints(self.lower_motion_paths, "lower")
            
            #cmds.parent(self.upper_twist_joints,start_joint )

            #cmds.parentConstraint(start_joint, self.upper_curve, mo=True)
            #cmds.parentConstraint(mid_joint, self.lower_curve, mo=True)

            # ---- ORGANIZACIÓN ----
            # general_twist_GRP: singleton — se crea solo si no existe todavía.
            # La primera extremidad lo crea; las siguientes lo reutilizan.
        general_twist_grp_name = "C_twist_GRP"
        if not cmds.objExists(general_twist_grp_name):
            self.general_twist_GRP = cmds.group(em=True, n=general_twist_grp_name)
        else:
            self.general_twist_GRP = general_twist_grp_name

            # twist_GRP individual por extremidad: recoge TODO excepto lowerTwistStart,
            # que debe quedarse emparentado bajo el bind mid_joint.
        twist_GRP = cmds.group(em=True, n=f"{self.side}_{self.name}_twist_GRP")

            # BaseDriver_CRV (la curva original renombrada, puede estar suelta)
        base_driver_crv = f"{self.side}_{self.name}BaseDriver_CRV"
        if cmds.objExists(base_driver_crv):
            if not cmds.listRelatives(base_driver_crv, parent=True):
                cmds.parent(base_driver_crv, twist_GRP)
        # Las curvas upper/lower solo se emparentan al twist_GRP si son propias de este módulo.
        # Si vienen del CurvatureModule (source_curve), ya viven en su propio grupo.
        if not source_curve:
            cmds.parent(self.upper_curve, self.lower_curve, twist_GRP)

            # Joints de twist (creados por create_twist_joints, nacen sueltos)
        for jnt in self.upper_twist_joints + self.lower_twist_joints:
            if cmds.objExists(jnt) and not cmds.listRelatives(jnt, parent=True):
                cmds.parent(jnt, twist_GRP)

            # nonroll_upper_start ya lleva dentro:
            #   - nonroll_upper_end
            #   - upper_twist_start (con upper_twist_end)
        nonroll_start = base_twist[0]  # nonroll_upper_start
        ik_handles    = base_twist[1:] # ik_hdl_upper, ik_hdl_upper_twist, ik_hdl_lower_twist

        if cmds.objExists(nonroll_start):
            if not cmds.listRelatives(nonroll_start, parent=True):
                cmds.parent(nonroll_start, twist_GRP)

            # IK handles sueltos
        for hdl in ik_handles:
            if cmds.objExists(hdl):
                if not cmds.listRelatives(hdl, parent=True):
                        cmds.parent(hdl, twist_GRP)

            # Emparentar el grupo individual bajo el general
        cmds.parent(twist_GRP, self.general_twist_GRP)

        self.twist_GRP = twist_GRP
            
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            current_parent = cmds.listRelatives(self.general_twist_GRP, parent=True)
            if not current_parent or current_parent[0] != rig_grp:
                cmds.parent(self.general_twist_GRP, rig_grp)
                
            
        return self.general_twist_GRP