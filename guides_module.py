import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import spine_module
import limbs_module
import fingers_module
import neck_module
import chest_module
import hip_module
import leg_module
import foot_module
import groups_module
import rigRoot_module
import mirror_module
import arm_right_module
import right_leg_module
import skinning_module
        
########################################################################
########################################################################
        
class SpineGuides(object):
    def __init__(self, spine_root, spine_chest, spine_position):
        self.spine_root = spine_root
        self.spine_end = spine_chest
        self.spine_position = spine_position
        self.guides_group = None 

    def spine_guides(self):
        root_joint = cmds.joint(p=(0, 0, 0), name=self.spine_root)
        if not root_joint:
            print(f"Error creando la joint: {self.spine_root}")
            return
        
        end_joint = cmds.joint(p=self.spine_position, name=self.spine_end)
        if not end_joint:
            print(f"Error creando la joint: {self.spine_end}")
            return

        cmds.select(root_joint, end_joint, r=True)
        self.guides_group = cmds.group(root_joint, n="spine_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grupo de guías.")
        
########################################################################
########################################################################
        
class NeckGuides(object):
    def __init__(self, neck_root, neck_end, root_pos, end_pos):
        self.neck_root = neck_root
        self.neck_end = neck_end
        self.root_pos = root_pos
        self.end_pos = end_pos
        self.guides_group = None 
    
    def neck_guides(self):
        cmds.select(clear=True)
        neck_root = cmds.joint(p=self.root_pos, n=self.neck_root)
        if not neck_root:
            print(f"Error creando la joint: {self.neck_root}")
            return
        
        neck_end = cmds.joint(p=self.end_pos, n=self.neck_end)
        if not neck_end:
            print(f"Error creando la joint: {self.neck_end}")
            return
        
        cmds.joint(neck_root, e=True, oj="yzx", sao="zup", ch=True, zso=True)
        self.guides_group = cmds.group(neck_root, n="neck_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grupo de guías del cuello.")
        
        cmds.select(clear = True)
        
########################################################################
########################################################################
        

class ArmGuides(object):
    """Clase base para extremidades (brazos y piernas)"""
    def __init__(self, limb_root, limb_mid, limb_end, clavicule_root,
                 limb_root_pos, limb_mid_pos, limb_end_pos, clavicule_root_pos):

        self.limb_root = limb_root
        self.limb_mid = limb_mid
        self.limb_end = limb_end
        self.clavicule = clavicule_root
        
        self.limb_root_pos = limb_root_pos
        self.limb_mid_pos = limb_mid_pos
        self.limb_end_pos = limb_end_pos
        self.clavicule_pos = clavicule_root_pos
        
        self.guides_group = None

    def create_chain(self):
        """Crea la cadena de joints y la orienta automáticamente"""
        cmds.select(clear=True)
        
        hierarchy_root = None
        
        if self.clavicule:
            hierarchy_root = cmds.joint(n=self.clavicule, p=self.clavicule_pos)

        root = cmds.joint(n=self.limb_root, p=self.limb_root_pos)
        mid = cmds.joint(n=self.limb_mid, p=self.limb_mid_pos)
        end = cmds.joint(n=self.limb_end, p=self.limb_end_pos)

        if not hierarchy_root:
            hierarchy_root = root

        # ORIENTACIÓN: Forzamos que el eje X apunte al siguiente joint
        # Esto soluciona que los joints 'salten' o se desorienten al escalar
        cmds.joint(root, edit=True, oj="xyz", sao="yup", ch=True, zso=True)
        
        self.guides_group = cmds.group(hierarchy_root, n="arm_guides_GRP")

        # El último joint (muñeca/tobillo) siempre debe tener orientación a cero
        #cmds.setAttr(f"{end}.jointOrient", 0, 0, 0)
        
        self.wrist_joint = self.limb_end 

        return self.guides_group

############################################################################
############################################################################
import maya.cmds as cmds

class LegGuides(object):
    """Clase base para extremidades (brazos y piernas)"""
    def __init__(self, limb_root, limb_mid, limb_end,
                 limb_root_pos, limb_mid_pos, limb_end_pos):

        self.limb_root = limb_root
        self.limb_mid = limb_mid
        self.limb_end = limb_end
        
        self.limb_root_pos = limb_root_pos
        self.limb_mid_pos = limb_mid_pos
        self.limb_end_pos = limb_end_pos
        
        self.guides_group = None

    def create_chain(self):
        """Crea la cadena de joints y la orienta automáticamente"""
        cmds.select(clear=True)
        
        hierarchy_root = None

        root = cmds.joint(n=self.limb_root, p=self.limb_root_pos)
        cmds.select(clear =True)
        mid = cmds.joint(n=self.limb_mid, p=self.limb_mid_pos)
        cmds.select(clear =True)
        end = cmds.joint(n=self.limb_end, p=self.limb_end_pos)
        cmds.select(clear =True)
        
        cmds.parent(mid,root)
        cmds.joint(root, edit=True, oj="xyz", sao="ydown", ch=True, zso=True)
        
        cmds.parent(end, mid)

        if not hierarchy_root:
            hierarchy_root = root

        # ORIENTACIÓN: Forzamos que el eje X apunte al siguiente joint
        # Esto soluciona que los joints 'salten' o se desorienten al escalar
        #cmds.joint(root, edit=True, oj="xyz", sao="ydown", ch=True, zso=True)
        
        self.guides_group = cmds.group(root, n="leg_guides_GRP")

        # El último joint (muñeca/tobillo) siempre debe tener orientación a cero
        cmds.setAttr(f"{end}.jointOrient", 0, 0, 0)
        
        self.ankle_joint = self.limb_end 

        return self.guides_group
        

       
                                             
########################################################################
########################################################################

class FingerGuides(object):

    def __init__(self, parent_joint, name, offsets):
        self.parent_joint = parent_joint
        self.name = name
        self.offsets = offsets
        self.joints = []

    def finger_guides(self):

        wrist_pos = cmds.xform(self.parent_joint, q=True, ws=True, t=True)
    
        cmds.select(clear=True)
    
        for i, offset in enumerate(self.offsets):
    
            pos = (
                wrist_pos[0] + offset[0],
                wrist_pos[1] + offset[1],
                wrist_pos[2] + offset[2]
            )
    
            jnt_name = f"{self.name}_{i+1:02d}"
            jnt = cmds.joint(n=jnt_name, p=pos)
    
            self.joints.append(jnt)
    
        # Parentar solo el root del dedo al wrist
        cmds.parent(self.joints[0], self.parent_joint)

############################################################
# HAND
############################################################

class HandGuides(object):

    def __init__(self, arm_instance):
        self.arm = arm_instance
        self.fingers = []
        self.group = None

    def hand_guides(self):

        wrist = self.arm.wrist_joint

        finger_data = {
            "L_index":  [(1,0,1),(2,0,1),(3,0,1),(4,0,1),(5,0,1)],
            "L_middle": [(1,0,0),(2,0,0),(3,0,0),(4,0,0),(5,0,0)],
            "L_ring":   [(1,0,-1),(2,0,-1),(3,0,-1),(4,0,-1),(5,0,-1)],
            "L_pinky":  [(1,0,-2),(2,0,-2),(3,0,-2),(4,0,-2),(5,0,-2)],
            "L_thumb":  [(1,-1,2),(2,-1,2),(3,-1,2)]
        }

        for name, offsets in finger_data.items():

            finger = FingerGuides(wrist, name, offsets)
            finger.finger_guides()
            self.fingers.append(finger)

        self.group = cmds.group(wrist, n="hand_guides_GRP")
        
        
############################################################
# FOOT
############################################################

class FootGuides(object):

    def __init__(self, leg_instance, ball_name, tip_name,heel_name,
                 ball_offset, tip_offset, heel_offset):
        self.leg = leg_instance
        self.ball_name = ball_name
        self.tip_name = tip_name
        self.heel_name = heel_name
        self.ball_offset = ball_offset
        self.tip_offset = tip_offset
        self.heel_offset = heel_offset
        self.joints = []

    def foot_guides(self):

        ankle = self.leg.ankle_joint
        ankle_pos = cmds.xform(ankle, q=True, ws=True, t=True)

        cmds.select(clear=True)
        
        #heel position
        heel_pos =(
            ankle_pos[0] + self.heel_offset[0],
            ankle_pos[1] + self.heel_offset[1],
            ankle_pos[2] + self.heel_offset[2]
        ) 
        
        heel= cmds.joint(n=self.heel_name, p=heel_pos)
        
        cmds.select(clear =True)
        
        # Ball position
        ball_pos = (
            ankle_pos[0] + self.ball_offset[0],
            ankle_pos[1] + self.ball_offset[1],
            ankle_pos[2] + self.ball_offset[2]
        )

        ball = cmds.joint(n=self.ball_name, p=ball_pos)

        # Tip position
        tip_pos = (
            ankle_pos[0] + self.tip_offset[0],
            ankle_pos[1] + self.tip_offset[1],
            ankle_pos[2] + self.tip_offset[2]
        )

        tip = cmds.joint(n=self.tip_name, p=tip_pos)

        self.joints = [ball, tip, heel]

        # Parentar ball al ankle
        cmds.parent(ball, ankle)
        cmds.parent(heel, ankle) 

##### INSTANCIAS #####

class CharacterGuides(object):
    def __init__(self):
        # Añadimos una variable para guardar la instancia del spine
        self.spine_rig = None
        
    def create_guides(self):

        spine_instance = SpineGuides("root", "chest", (0, 10, 0))
        spine_instance.spine_guides()

        neck_instance = NeckGuides("neck_root","neck_end",(0, 20, 0), (0, 23, 0.5))
        neck_instance.neck_guides()

        arm_instance = ArmGuides(
            "L_shoulder", "L_elbow", "L_wrist","L_clavicule",
            (3, 12, 0),
            (13, 12, -0.1),
            (23, 12, 0),
            (0,12,0)
        )
        arm_instance.create_chain()

        leg_instance = LegGuides(
            "L_hip", "L_knee", "L_ankle",
            (3, -10, 0),
            (3, -20, 0.2),
            (3, -30, 0)
        )
        leg_instance.create_chain()

        hand_instance = HandGuides(arm_instance)
        hand_instance.hand_guides()

        foot_instance = FootGuides(
            leg_instance,
            "L_ball",
            "L_toe_tip",
            "L_heel",
            (0, -2, 3),
            (0, -2, 6),
            (0,-2,-3)
        )
        foot_instance.foot_guides()
        
