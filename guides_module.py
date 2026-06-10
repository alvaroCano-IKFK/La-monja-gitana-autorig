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
#SPINE
########################################################################
        
class SpineGuides(object):
    """
    Crea les guies de la spine.

    """
    def __init__(self, spine_root, spine_chest, spine_position):
        self.spine_root = spine_root
        self.spine_end = spine_chest
        self.spine_position = spine_position
        self.guides_group = None 

    def spine_guides(self):
        #Crea el joint root de les guies de la spine
        root_joint = cmds.joint(p=(0, 3, -15), name=self.spine_root)
        if not root_joint:
            print(f"Error creando la joint: {self.spine_root}")
            return
        
        #Crea el joint final de les guies de la spine
        end_joint = cmds.joint(p=self.spine_position, name=self.spine_end)
        if not end_joint:
            print(f"Error creando la joint: {self.spine_end}")
            return

        #Crea el grup de les guies de la spine
        cmds.select(root_joint, end_joint, r=True)
        self.guides_group = cmds.group(root_joint, n="spine_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grupo de guías.")
        
########################################################################
#NECK
########################################################################
        
class NeckGuides(object):
    """
    Crea les guies del coll.

    """
    def __init__(self, neck_root, neck_end, root_pos, end_pos):
        self.neck_root = neck_root
        self.neck_end = neck_end
        self.root_pos = root_pos
        self.end_pos = end_pos
        self.guides_group = None 
    
    def neck_guides(self):
        cmds.select(clear=True)
        #Crea el joint d inici de la guia del neck
        neck_root = cmds.joint(p=self.root_pos, n=self.neck_root)
        if not neck_root:
            print(f"Error creando la joint: {self.neck_root}")
            return
        
        #Crea el joint del final de la guia del neck
        neck_end = cmds.joint(p=self.end_pos, n=self.neck_end)
        if not neck_end:
            print(f"Error creando la joint: {self.neck_end}")
            return
        
        cmds.joint(neck_root, e=True, oj="yzx", sao="zup", ch=True, zso=True)
        cmds.setAttr(f"{neck_end}.jointOrientX", 0)
        cmds.setAttr(f"{neck_end}.jointOrientY", 0)
        cmds.setAttr(f"{neck_end}.jointOrientZ", 0)
        
        #Crea el grup de les guies del coll
        self.guides_group = cmds.group(neck_root, n="neck_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grupo de guías del cuello.")
        
        cmds.select(clear = True)
        
########################################################################
#LIMB
########################################################################
        
class LimbGuides(object):
    """
    Classe per crear les guies dels bracos i cames.

    """
    def __init__(self, limb_root, limb_mid, limb_end,
                 limb_root_pos, limb_mid_pos, limb_end_pos):

        self.limb_root = limb_root
        self.limb_mid = limb_mid
        self.limb_end = limb_end
        
        self.limb_root_pos = limb_root_pos
        self.limb_mid_pos = limb_mid_pos
        self.limb_end_pos = limb_end_pos
        
        self.joint_orient = "xzy"   
        self.up_axis      = "zdown"  
        
        self.guides_group = None
    
    def create_chain(self):
        """
        Crea la cadena de joints i la orienta automaticament

        """
        cmds.select(clear=True)
        
        hierarchy_root = None

        #Crea tres joints, d inici, mig i final 
        root = cmds.joint(n=self.limb_root, p=self.limb_root_pos)
        mid = cmds.joint(n=self.limb_mid, p=self.limb_mid_pos)
        end = cmds.joint(n=self.limb_end, p=self.limb_end_pos)

        if not hierarchy_root:
            hierarchy_root = root

        # Força a que els joints apuntin sempre en l eix X
        cmds.joint(root, edit=True, oj=self.joint_orient, sao=self.up_axis, ch=True, zso=True)

        #Crea el grup de limb        
        self.guides_group = cmds.group(hierarchy_root, n="limb_guides_GRP")

        # L ultim joint s orienta sempre tot a 0
        cmds.setAttr(f"{end}.jointOrient", 0, 0, 0)
        
        return self.guides_group


############################################################################
#LEG
############################################################################

class LegGuides(LimbGuides):
    """
    Hereda de la classe limbs i fa la cama
    """
    def __init__(self, clavicule_start,clavicule_root,limb_root, limb_mid, limb_end,
                 clavicule_start_pos, clavicule_root_pos,limb_root_pos, limb_mid_pos, limb_end_pos):
        
        super(LegGuides, self).__init__(limb_root, limb_mid, limb_end, limb_root_pos, limb_mid_pos, limb_end_pos)
                
        self.shoulder_joint = self.limb_root
        self.elbow_joint    = self.limb_mid
        self.wrist_joint    = self.limb_end
        
        self.clavicule_start = clavicule_start
        self.clavicule_start_pos = clavicule_start_pos
        
        self.clavicule = clavicule_root
        self.clavicule_pos = clavicule_root_pos
        
        #Configura el grup, l’orientacio i el joint final de la cama
        self.group_name = "leg_guides_GRP"
        self.joint_orient = "xzy"
        self.up_axis = "zdown"
        self.ankle_joint = self.limb_end
        
    def create_chain(self):
        """
        Orden final: clavicule_start -> clavicule -> hip -> knee -> ankle
        """
        cmds.select(clear=True)

        # 1. Crea la cadena principal: hip -> knee -> ankle
        hip   = cmds.joint(n=self.limb_root, p=self.limb_root_pos)
        knee  = cmds.joint(n=self.limb_mid,  p=self.limb_mid_pos)
        ankle = cmds.joint(n=self.limb_end,  p=self.limb_end_pos)

        cmds.joint(hip, edit=True, oj=self.joint_orient, sao=self.up_axis, ch=True, zso=True)
        cmds.setAttr(f"{ankle}.jointOrient", 0, 0, 0)

        # 2. Crea clavicule y clavicule_start por encima
        cmds.select(clear=True)
        clav_start = cmds.joint(n=self.clavicule_start, p=self.clavicule_start_pos)
        clav       = cmds.joint(n=self.clavicule,       p=self.clavicule_pos)

        # 3. Emparenta hip bajo clavicule
        cmds.parent(hip, clav)

        # 4. Orienta toda la cadena desde la raíz
        cmds.joint(clav_start, edit=True, oj=self.joint_orient, sao=self.up_axis, ch=True, zso=True)
        cmds.setAttr(f"{ankle}.jointOrient", 0, 0, 0)

        # 5. Grupo con clavicule_start como raíz
        self.guides_group = cmds.group(clav_start, n="leg_guides_GRP")

        return self.guides_group
    
class BackLegGuides(LegGuides): 
    def __init__(self, clavicule_start, limb_root, limb_mid, limb_end,
                 clavicule_start_pos, limb_root_pos, limb_mid_pos, limb_end_pos):
        
        super(BackLegGuides, self).__init__(
            clavicule_start, clavicule_start,   # passa clavicule_start dos vegades per no trencar LegGuides
            limb_root, limb_mid, limb_end,
            clavicule_start_pos, clavicule_start_pos,  # idem amb la pos
            limb_root_pos, limb_mid_pos, limb_end_pos
        )
        self.group_name = "back_leg_guides_GRP"

    def create_chain(self):
        """
        Cadena sense clavicule: clavicule_start -> hip -> knee -> ankle
        """
        cmds.select(clear=True)

        hip   = cmds.joint(n=self.limb_root, p=self.limb_root_pos)
        knee  = cmds.joint(n=self.limb_mid,  p=self.limb_mid_pos)
        ankle = cmds.joint(n=self.limb_end,  p=self.limb_end_pos)

        cmds.joint(hip, edit=True, oj=self.joint_orient, sao=self.up_axis, ch=True, zso=True)
        cmds.setAttr(f"{ankle}.jointOrient", 0, 0, 0)

        cmds.select(clear=True)
        clav_start = cmds.joint(n=self.clavicule_start, p=self.clavicule_start_pos)

        # Hip directament sota clavicule_start (sense clavicule intermedi)
        cmds.parent(hip, clav_start)

        cmds.joint(clav_start, edit=True, oj=self.joint_orient, sao=self.up_axis, ch=True, zso=True)
        cmds.setAttr(f"{ankle}.jointOrient", 0, 0, 0)

        self.guides_group = cmds.group(clav_start, n=self.group_name)

        return self.guides_group
############################################################
#FOOT
############################################################

class FootGuides(object):
    """
    Crea les guies del peu. 

    """

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
        
        #Ball position
        ball_pos = (
            ankle_pos[0] + self.ball_offset[0],
            ankle_pos[1] + self.ball_offset[1],
            ankle_pos[2] + self.ball_offset[2]
        )

        ball = cmds.joint(n=self.ball_name, p=ball_pos)

        #Tip position
        tip_pos = (
            ankle_pos[0] + self.tip_offset[0],
            ankle_pos[1] + self.tip_offset[1],
            ankle_pos[2] + self.tip_offset[2]
        )

        tip = cmds.joint(n=self.tip_name, p=tip_pos)

        self.joints = [ball, tip, heel]

        #Parentar ball al ankle
        cmds.parent(ball, ankle)
        cmds.parent(heel, ankle) 

##### INSTANCIAS #####

class CharacterGuides(object):
    """Esta clase se encarga de crear todas las guías del personaje y agruparlas bajo un grupo principal llamado "guides_GRP"."""
    
    def __init__(self):
        # Añadimos una variable para guardar la instancia del spine
        self.spine_rig = None
        self.all_guides_grp = None
        
    def create_guides(self):
        """
        Aquesta funcio crea totes les guies del personatge i les agrupa sota un grup principal anomenat "guides_GRP".

        """
        #Crea les guies de la spine
        spine_instance = SpineGuides("root", "chest", (0, 3, 11))
        spine_instance.spine_guides()

        #Crea les guies del coll
        neck_instance = NeckGuides("neck_root","neck_end",(0, 3, 11), (0, 20, 23))
        neck_instance.neck_guides()



        #Crea les guies de la cama
        leg_instance = LegGuides(
            "L_clavicule_start","L_clavicule","L_hip", "L_knee", "L_ankle",
            (3.6,3,10),
            (3.6,-2,14),
            (3.6, -10, 12),
            (3.6, -18, 12),
            (3.6, -27, 12)
        )
        leg_instance.create_chain()
        
        back_leg_instance = BackLegGuides(
            "L_clavicule_start_back","L_hip_back", "L_knee_back", "L_ankle_back",
            (3.6,2,-17),
            (3.6, -5, -14),
            (3.6, -16.5, -19),
            (3.6, -27, -19.5)
        )
        back_leg_instance.create_chain()



        #Crea les guies del peu a partir de la cama
        foot_instance = FootGuides(
            leg_instance,
            "L_ball",
            "L_toe_tip",
            "L_heel",
            (0, -2, 1),
            (0, -5, 3),
            (0,-5,-3)
        )
        foot_instance.foot_guides()
        
        back_foot_instance = FootGuides(
            back_leg_instance,
            "L_ball_back",
            "L_toe_tip_back",
            "L_heel_back",
            (0, -2, 1),
            (0, -5, 3),
            (0, -5, -3)
        )
        back_foot_instance.foot_guides()
       
        #Llista amb tots els grups de guies creats       
        guide_groups = [
            spine_instance.guides_group,
            neck_instance.guides_group,
            leg_instance.guides_group,
            back_leg_instance.guides_group,
         ]

        # Filtra nomes els grups que existeixen
        new_list = []
        
        for g in guide_groups:
            if g and cmds.objExists(g):
                new_list.append(g)
        guide_groups = new_list

        #Si no hi ha grups valids, mostra un warining
        if not guide_groups:
            cmds.warning("No se encontraron grupos de guías para agrupar.")
            return

        #Agrupa totes les guies sota un únic grup principal
        self.all_guides_grp = cmds.group(guide_groups, n="guides_GRP")
        cmds.setAttr(f"{self.all_guides_grp}.translateY", 32.5)

        
