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
import guides_module


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