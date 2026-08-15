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
        root_joint = cmds.joint(p=(0, 0, 0), name=self.spine_root)
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
        
        self.joint_orient = "xyz"   
        self.up_axis      = "yup"  
        
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

########################################################################
#ARM
########################################################################

class ArmGuides(LimbGuides):
    """
    Hereda de la classe limbs i crea la clavicula, completant el brac
    """
    def __init__(self, limb_root, limb_mid, limb_end, clavicule_root,
                 limb_root_pos, limb_mid_pos, limb_end_pos, clavicule_root_pos):

        super(ArmGuides, self).__init__(
            limb_root, limb_mid, limb_end,
            limb_root_pos, limb_mid_pos, limb_end_pos
        )

        self.clavicule = clavicule_root
        self.clavicule_pos = clavicule_root_pos
        
        self.shoulder_joint = self.limb_root
        self.elbow_joint    = self.limb_mid
        self.wrist_joint    = self.limb_end

    def create_chain(self):
        """
        Crea la clavicula 

        """
        super(ArmGuides, self).create_chain()

        root = self.limb_root
        end  = self.limb_end

        if self.clavicule:
            cmds.select(clear=True)
            #Crea el joint de la clavicula
            hierarchy_root = cmds.joint(n=self.clavicule, p=self.clavicule_pos)

            #Emparenta la clavicula amb el primer joint del brac
            cmds.parent(root, hierarchy_root)

            cmds.joint(hierarchy_root, edit=True, oj=self.joint_orient, sao=self.up_axis, ch=True, zso=True)
            #cmds.setAttr(f"{end}.jointOrient", 0, 0, 0)  

            cmds.parent(root, world=True)
            cmds.delete(self.guides_group)

            #Crea el grup de guies del brac 
            cmds.parent(root, hierarchy_root)
            self.guides_group = cmds.group(hierarchy_root, n="arm_guides_GRP")

        return self.guides_group

############################################################################
#LEG
############################################################################

class LegGuides(LimbGuides):
    """
    Hereda de la classe limbs i fa la cama
    """
    def __init__(self, limb_root, limb_mid, limb_end,
                 limb_root_pos, limb_mid_pos, limb_end_pos):
        
        super(LegGuides, self).__init__(limb_root, limb_mid, limb_end, limb_root_pos, limb_mid_pos, limb_end_pos)
        
        #Configura el grup, l’orientacio i el joint final de la cama
        self.group_name = "leg_guides_GRP"
        self.joint_orient = "xzy"
        self.up_axis = "zdown"
        self.ankle_joint = self.limb_end

                                             
########################################################################
#FINGER
########################################################################

class FingerGuides(object):
    """
    Crea les guies dels dits. 

    """

    def __init__(self, parent_joint, name, offsets):
        self.parent_joint = parent_joint
        self.name = name
        self.offsets = offsets
        self.joints = []

    def finger_guides(self):
        #Agafa la posicio del joint del canell 
        wrist_pos = cmds.xform(self.parent_joint, q=True, ws=True, t=True)
    
        cmds.select(clear=True)
        
        #Crea els joints dels dits a partir de les dades definides
        for i, offset in enumerate(self.offsets):
    
            pos = (
                wrist_pos[0] + offset[0],
                wrist_pos[1] + offset[1],
                wrist_pos[2] + offset[2]
            )
    
            jnt_name = f"{self.name}_{i+1:02d}"
            jnt = cmds.joint(n=jnt_name, p=pos)
    
            self.joints.append(jnt)
    
        #Emparentar el root del dit amb el canell
        cmds.parent(self.joints[0], self.parent_joint)

############################################################
# HAND
############################################################

class HandGuides(object):
    """
    Crea les guies de la ma.

    """

    def __init__(self, arm_instance):
        self.arm = arm_instance
        self.fingers = []
        self.group = None

    def hand_guides(self):
        
        #Agafa el joint del canel
        wrist = self.arm.wrist_joint

        #Dades dels dits
        finger_data = {
            "L_index":  [(1,0,1),(2,0,1),(3,0,1),(4,0,1),(5,0,1)],
            "L_middle": [(1,0,0),(2,0,0),(3,0,0),(4,0,0),(5,0,0)],
            "L_ring":   [(1,0,-1),(2,0,-1),(3,0,-1),(4,0,-1),(5,0,-1)],
            "L_pinky":  [(1,0,-2),(2,0,-2),(3,0,-2),(4,0,-2),(5,0,-2)],
            "L_thumb":  [(1,0,1),(1,-1,2),(2,-1,2),(3,-1,2)]
        }
        


        #Crea les guies dels dits a partir de les dades definides
        for name, offsets in finger_data.items():

            finger = FingerGuides(wrist, name, offsets)
            finger.finger_guides()
            self.fingers.append(finger)
            
        # =========================================================================
        # RE-ORIENTACIÓN ANATÓMICA DEL PULGAR (Para comodidad del animador)
        # =========================================================================
        
        # --- LADO IZQUIERDO (L) ---
        # Asegúrate de que estos nombres coinciden con los que genera tu rig de guías
        thumb_l_root = "L_thumb_01"   # O "L_thumb_1", revisa tu Outliner
        thumb_l_med  = "L_thumb_02"   # O "L_thumb_2"
        
        if cmds.objExists(thumb_l_root) and cmds.objExists(thumb_l_med):
            # 1. Almacenamos el abuelo (wrist) para no perder la jerarquía superior
            parent_wrist = cmds.listRelatives(thumb_l_root, parent=True)[0]
            
            # 2. Desemparentamos el hijo temporalmente para que no se mueva de su posición en el espacio
            cmds.parent(thumb_l_med, world=True)
            
            # 3. Forzamos la orientación base del eje X hacia donde estaba el hijo
            cmds.joint(thumb_l_root, edit=True, oj="xyz", sao="yup", zso=True)
            
            # 4. Metemos el TWIST en el Joint Orient X para encarar el eje de flexión hacia la palma
            # Ajusta este valor (ej. 30, 45, 60) hasta que veas que el eje Z o Y apunta hacia donde se cierra el puño
            cmds.setAttr(f"{thumb_l_root}.jointOrientY", -90)
            
            # 5. Volvemos a emparentar la cadena del pulgar
            cmds.parent(thumb_l_med, thumb_l_root)
            
            # 6. Limpiamos al hijo para que su orientación mire recta hacia la punta del pulgar
            cmds.joint(thumb_l_med, edit=True, oj="xyz", sao="yup", ch=True, zso=True)
        #Agrupa les guies de la ma
        #self.group = cmds.group(wrist, n="hand_guides_GRP")
        
        
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

############################################################
#BOCA🫦
############################################################
class BocaGuides(object):
    """
    Genera los jointsa de la boca y la surface
    """
    def __init__(self, lips_NRB,lip_mid, lip_end):
        self.boca_surface = lips_NRB
        self.lip_mid = lip_mid
        self.lip_end = lip_end
        
    def create_boca(self):
        #Crea la surface de la boca
        surface = cmds.nurbsPlane(n=self.boca_surface, ax=(0, 1, 0), w=10, lr=1, d=1, u=4, v=4)[0]
        cmds.setAttr(f"{surface}.translateY", 24)
        cmds.setAttr(f"{surface}.translateZ", 10)
        cmds.setAttr(f"{surface}.rotateX", 90)
        
        #Dar una posición base a la forma de la nurbs
        cmds.select(surface + ".cv[4][0:4]", r=True)
        cmds.select(surface + ".cv[0][0:4]", add=True)
        cmds.move(0, 0, -4, r=True)
        
        cmds.select(surface + ".cv[1][0:4]", r=True)
        cmds.select(surface + ".cv[3][0:4]", add=True)
        cmds.move(0, 0, -1, r=True)
        
        #Crea els joints de la boca
        cmds.select(clear=True)
        lip_mid_joint = cmds.joint(n=self.lip_mid, p=(0, 24, 10))
        cmds.select(clear=True)
        lip_end_joint = cmds.joint(n=self.lip_end, p=(2.5, 24, 9))
        cmds.setAttr(f"{lip_end_joint}.rotateY", 45)
        
        self.guides_group = cmds.group(surface, lip_mid_joint, lip_end_joint, n="boca_guides_GRP")
        return self.guides_group
        
class JawGuides(object):
    """
    Crea les guies de la jaw.
    """
    def __init__(self, jaw_root, jaw_end, root_pos, end_pos):
        self.jaw_root = jaw_root
        self.jaw_end = jaw_end
        self.root_pos = root_pos
        self.end_pos = end_pos
        self.guides_group = None

    def jaw_guides(self):
        cmds.select(clear=True)

        # Crea el joint root de les guies de la jaw
        rootJaw_joint = cmds.joint(p=self.root_pos, name=self.jaw_root)
        if not rootJaw_joint:
            print(f"Error creando la joint: {self.jaw_root}")
            return

        # Crea el joint final de les guies de la jaw
        endJaw_joint = cmds.joint(p=self.end_pos, name=self.jaw_end)
        if not endJaw_joint:
            print(f"Error creando la joint: {self.jaw_end}")
            return

        # Crea el grup de les guies de la jaw
        self.guides_group = cmds.group(rootJaw_joint, n="jaw_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grupo de guías de la jaw.")

        cmds.select(clear=True)  

#########################################################################
#EYEBROWS
#########################################################################

class EyebrowsGuides(object):
    """
    Crea automàticament 10 guies de les celles a partir de les posicions de referència.
    """
    def __init__(self, eyebrow_root, eyebrow_end, root_pos=(0, 24, 10), end_pos=(2.5, 24, 9)):
        self.eyebrow_root = eyebrow_root
        self.eyebrow_end = eyebrow_end
        self.root_pos = root_pos
        self.end_pos = end_pos
        self.guides_group = None

    def eyebrows_guides(self):
        cmds.select(clear=True)
        
        created_joints = []
        num_joints = 10  

        for i in range(num_joints):
            t = i / float(num_joints - 1)
            
            current_pos = [
                round(self.root_pos[j] + (self.end_pos[j] - self.root_pos[j]) * t, 4)
                for j in range(3)
            ]

            joint_name = f"{self.eyebrow_root}_{i+1:02d}"
            
            current_joint = cmds.joint(p=current_pos, name=joint_name)
            if not current_joint:
                print(f"Error creant el joint: {joint_name}")
                return
                
            created_joints.append(current_joint)

        self.guides_group = cmds.group(created_joints, n="eyebrows_guides_GRP")
        if self.guides_group is None:
            print("Error al crear el grup de guies de les celles.")

        cmds.select(clear=True)
        return self.guides_group

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
        spine_instance = SpineGuides("root", "chest", (0, 10, 0))
        spine_instance.spine_guides()

        #Crea les guies del coll
        neck_instance = NeckGuides("neck_root","neck_end",(0, 20, 0), (0, 23, 0.5))
        neck_instance.neck_guides()

        #Crea les guies del brac
        arm_instance = ArmGuides(
            "L_shoulder", "L_elbow", "L_wrist","L_clavicule",
            (3, 12, 0),
            (13, 12, -0.1),
            (23, 12, 0),
            (0,12,0)
        )
        arm_instance.create_chain()

        #Crea les guies de la cama
        leg_instance = LegGuides(
            "L_hip", "L_knee", "L_ankle",
            (3, -10, 0),
            (3, -20, 0.2),
            (3, -30, 0)
        )
        leg_instance.create_chain()

        #Crea les guies de la ma a partir del brac
        hand_instance = HandGuides(arm_instance)
        hand_instance.hand_guides()

        #Crea les guies del peu a partir de la cama
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
       
       
        #Crea les guies de la boca
        boca_instance = BocaGuides("boca_surface", "C_lip_mid", "L_lip_end")
        boca_instance.create_boca()
        
        #Crea les guies de la jaw
        jaw_instance = JawGuides("jaw_root", "jaw_end", (0, 21, 5),(0, 19, 9))
        jaw_instance.jaw_guides()

        #Crea les guies de les celles
        eyebrows_instance = EyebrowsGuides("L_eyebrow_root", "L_eyebrow_end", root_pos=(0, 34, 10), end_pos=(0, 34, 9))
        eyebrows_instance.eyebrows_guides()
        
        #Llista amb tots els grups de guies creats       
        guide_groups = [
            spine_instance.guides_group,
            neck_instance.guides_group,
            arm_instance.guides_group,
            leg_instance.guides_group,
            hand_instance.group,
            boca_instance.guides_group,
            jaw_instance.guides_group,
            eyebrows_instance.guides_group
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

        
