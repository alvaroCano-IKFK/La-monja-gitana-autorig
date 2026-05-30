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

        # Forca a que els joints apuntin sempre en l eix X
        cmds.joint(root, edit=True, oj="xyz", sao="yup", ch=True, zso=True)

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

            cmds.joint(hierarchy_root, edit=True, oj="xyz", sao="yup", ch=True, zso=True)
            cmds.setAttr(f"{end}.jointOrient", 0, 0, 0)  

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
        self.up_axis = "ydown"
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
            "L_thumb":  [(1,-1,2),(2,-1,2),(3,-1,2)]
        }

        #Crea les guies dels dits a partir de les dades definides
        for name, offsets in finger_data.items():

            finger = FingerGuides(wrist, name, offsets)
            finger.finger_guides()
            self.fingers.append(finger)

        #Agrupa les guies de la ma
        self.group = cmds.group(wrist, n="hand_guides_GRP")
        
        
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
        
        cmds.joint(ankle, edit=True, oj="xzy", sao="zdown", ch=True,zso = True)

##### INSTANCIAS #####

class CharacterGuides(object):
    """
    
    """
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
            (3, -20, 0.1),
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
       
        #Llista amb tots els grups de guies creats       
        guide_groups = [
            spine_instance.guides_group,
            neck_instance.guides_group,
            arm_instance.guides_group,
            leg_instance.guides_group,
            hand_instance.group,
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

        
    def build(self):
        """Este es el método que llama el botón BUILD de la UI"""
        print("Iniciando construcción del Rig...")
        
        # 0. CONSTRUIR ROOT RIG (NUEVO - va primero)
        self.root_rig = rigRoot_module.RigRoot(rig_name="Character")
        self.root_rig.build()
        #self.root_rig.mirrorControls()
        
        # 1. CONSTRUIR ESPINA
        self.spine_rig = spine_module.SpineModule(
            root_guide="root", 
            chest_guide="chest", 
            rig_name="Character",
            root_instance=self.root_rig
        )
        self.spine_rig.build()
        
        # 2. CONSTRUIR BRAZO (Aquí estaba el fallo, faltaba llamar al módulo)
        # Usamos los nombres que definiste en create_guides: "shoulder", "elbow", "wrist"
        self.arm_rig = limbs_module.LimbModule(
            shoulder_guide="L_shoulder",
            elbow_guide="L_elbow",
            wrist_guide="L_wrist",
            clavicule_guide="L_clavicule",
            rig_name="Arm_L",
            root_instance=self.root_rig
        )
        self.arm_rig.build()
        
        # --- BRAZO DERECHO (El nuevo) ---
        self.right_arm_rig = arm_right_module.ArmRightModule(
            rig_name="Arm_R", 
            left_arm_instance=self.arm_rig,
            root_instance=self.root_rig
        )
        self.right_arm_rig.build()
               


        #4. CONSTRRUIR DEDOS
        self.fingers_rig = fingers_module.FingersModule( wrist_guide="L_wrist", rig_name ="Arm_L",root_instance=self.root_rig)
        self.fingers_rig.build()
        
        # Modifica LimbModule para que guarde self.b_sh al terminar build.
        shoulder_jnt = "Arm_L_shoulder_bind_JNT"
        
        # CONSTRUIR CUELLO
        # Aquí le pasas exactamente los nombres que usaste en NeckGuides: "neck_root" y "neck_end"
        self.neck_rig = neck_module.NeckModule(
            neck_root="neck_root", 
            neck_end="neck_end", 
            rig_name="Character",
            root_instance=self.root_rig
        )
        self.neck_rig.build()
                
        #CONSTRUIR CHEST
        
        self.chest_rig = chest_module.ChestModule(chest_guide = "chest",root_instance=self.root_rig)
        
        self.chest_rig.build()
        
        #CONSTRRUIR HIP
        
        self.hip_rig = hip_module.HipModule(root_guide ="root",root_instance=self.root_rig)
        
        self.hip_rig.build()
        
        # Dedos R (las guías ya existen porque son hijos de R_wrist)
        self.fingers_rig.build_mirror()

        # En el método build de CharacterGuides
        self.leg_rig = leg_module.LegModule(
            thigh_guide="L_hip",
            knee_guide="L_knee",
            ankle_guide="L_ankle",
            ball_guide="L_ball",
            tip_guide="L_toe_tip",
            heel_guide="L_heel",
            rig_name="Leg_L",
            root_instance=self.root_rig
        )
        self.leg_rig.build()

        # Solo dos líneas: instanciar y construir.
        # --- PIERNA DERECHA (Aquí estaba el error) ---
        # Cambiamos L_leg por self.leg_rig que es la instancia real
        self.right_leg_rig = right_leg_module.LegRightModule(
            rig_name="Leg_R", 
            left_leg_instance=self.leg_rig, # Corregido: usamos la instancia de arriba
            root_instance=self.root_rig
        )
        self.right_leg_rig.build()
        

        # Importamos el nuevo módulo y ejecutamos
        skn = skinning_module.SkinningModule(
            rig_name="Character",
            root_instance=self.root_rig
        )
        skn.build()
                       
        print("Build completo: Spine, Arm y Leg construidos.")