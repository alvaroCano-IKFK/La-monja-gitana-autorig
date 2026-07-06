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
import skinning_module
import guides_module
import build_module
import body_module
import spaceSwitching_module
import headSpace_module
import curvature_module
import soft_module



class BuildRig(object):
    
    def build(self):
        """Este es el método que llama el botón BUILD de la UI"""
        print("Iniciando construcción del Rig...")
        #Llista amb tots els grups de guies creats       
    
        # 0. CONSTRUIR ROOT RIG (NUEVO - va primero)
        self.root_rig = rigRoot_module.RigRoot(rig_name="Character")
        self.root_rig.build()
        #self.root_rig.mirrorControls()

        # 0. CONSTRUIR BODY
        self.body_rig = body_module.BodyModule(
                rig_name="Character",
                root_instance=self.root_rig
            )    
        self.body_rig.build()   


        # 1. CONSTRUIR ESPINA
        self.spine_rig = spine_module.SpineModule(
                root_guide="root", 
                chest_guide="chest", 
                rig_name="Character",
                root_instance=self.root_rig
            )
        self.spine_rig.build()

        #CONSTRUIR CHEST
            
        self.chest_rig = chest_module.ChestModule(chest_guide = "chest",root_instance=self.root_rig)
            
        self.chest_rig.build()   

        # 2. CONSTRUIR BRAZO (Aquí estaba el fallo, faltaba llamar al módulo)
        self.arm_rig = limbs_module.LimbModule(
                shoulder_guide="L_shoulder",
                elbow_guide="L_elbow",
                wrist_guide="L_wrist",
                clavicule_guide="L_clavicule",
                rig_name="Arm",
                side="L",
                root_instance=self.root_rig
            )
        self.arm_rig.build()
        
        self.mirror_arm_rig = limbs_module.LimbModule(
                shoulder_guide="R_shoulder",
                elbow_guide="R_elbow",
                wrist_guide="R_wrist",
                clavicule_guide="R_clavicule",
                rig_name="Arm",
                side="R",
                root_instance=self.root_rig
                    )
        self.mirror_arm_rig.build()
        


        #4. CONSTRRUIR DEDOS
        self.fingers_rig = fingers_module.FingersModule( 
                wrist_guide="L_wrist", 
                rig_name ="Arm",
                side = "L",
                root_instance=self.root_rig)
        self.fingers_rig.build()
        
        self.mirror_fingers_rig = fingers_module.FingersModule(
                wrist_guide="R_wrist",
                rig_name="Arm",
                side="R",
                root_instance=self.root_rig)
        self.mirror_fingers_rig.build()
            
        # Modifica LimbModule para que guarde self.b_sh al terminar build.
        shoulder_jnt = "L_Arm_shoulder_bind_JNT"
            
        # CONSTRUIR CUELLO
        self.neck_rig = neck_module.NeckModule(
                neck_root="neck_root", 
                neck_end="neck_end", 
                rig_name="Character",
                root_instance=self.root_rig
            )
        self.neck_rig.build()
            
        #CONSTRRUIR HIP
            
        self.hip_rig = hip_module.HipModule(root_guide ="root",root_instance=self.root_rig)
            
        self.hip_rig.build()
            

        # En el método build de CharacterGuides
        self.leg_rig = leg_module.LegModule(
                thigh_guide="L_hip",
                knee_guide="L_knee",
                ankle_guide="L_ankle",
                ball_guide="L_ball",
                tip_guide="L_toe_tip",
                heel_guide="L_heel",
                rig_name="Leg",
                root_instance=self.root_rig,
                hip_instance=self.hip_rig
            )
        self.leg_rig.build()

        self.mirror_leg_rig = leg_module.LegModule(
                thigh_guide="R_hip",
                knee_guide="R_knee",
                ankle_guide="R_ankle",
                ball_guide="R_ball",
                tip_guide="R_toe_tip",
                heel_guide="R_heel",
                rig_name="Leg",
                side="R", 
                root_instance=self.root_rig,
                hip_instance=self.hip_rig
            )
        self.mirror_leg_rig.build() 


        # Importamos el módulo de skinning
        skn = skinning_module.SkinningModule(
                rig_name="Character",
                root_instance=self.root_rig
            )
        skn.build()
        
        soft_leg_L = soft_module.SoftIkModule(side="L", prefix="Leg")
        soft_leg_L.apply_soft_ik(
            ik_ctrl="L_Leg_legIk_CTRL",
            ik_handle="L_Leg_IKH",
            root_ctrl="L_Leg_legRoot_CTRL",
            root_jnt="L_Leg_thigh_ik_JNT",
            mid_jnt="L_Leg_knee_ik_JNT",
            global_ctrl="Character_global_CTL",
            ik_hdl="L_Leg_IKH"
        )
        
        soft_leg_R = soft_module.SoftIkModule(side="R", prefix="Leg")
        soft_leg_R.apply_soft_ik(
            ik_ctrl="R_Leg_legIk_CTRL",
            ik_handle="R_Leg_IKH",
            root_ctrl="R_Leg_legRoot_CTRL",
            root_jnt="R_Leg_thigh_ik_JNT",
            mid_jnt="R_Leg_knee_ik_JNT",
            global_ctrl="Character_global_CTL",
            ik_hdl="R_Leg_IKH"
        )

        soft_arm_L = soft_module.SoftIkModule(side="L", prefix="Arm")
        soft_arm_L.apply_soft_ik(
            ik_ctrl="L_Arm_armIk_CTRL",
            ik_handle="L_Arm_IKH",
            root_ctrl="L_Arm_armRoot_CTRL",
            mid_jnt="L_Arm_elbow_ik_JNT",
            root_jnt="L_Arm_shoulder_ik_JNT",
            global_ctrl="Character_global_CTL",
            ik_hdl="L_Arm_IKH"

        )
        
        soft_arm_R = soft_module.SoftIkModule(side="R", prefix="Arm")
        soft_arm_R.apply_soft_ik(
            ik_ctrl="R_Arm_armIk_CTRL",
            ik_handle="R_Arm_IKH",
            root_ctrl="R_Arm_armRoot_CTRL",
            mid_jnt="R_Arm_elbow_ik_JNT",
            root_jnt="R_Arm_shoulder_ik_JNT",
            global_ctrl="Character_global_CTL",
            ik_hdl="R_Arm_IKH"
            
        )                
        

        # =========================================================================
        # CONFIGURACIÓN DE SPACES (DYNAMIC PARENTS) - ANTES DEL SKINNING
        # =========================================================================
        print("[Spaces] Iniciando la creación de sistemas Dynamic Parent (_SPC)...")

        # 2. Espacios para las Manos IK (Brazos)
        # Recorremos ambos lados para aplicar los espacios a los controles IK de las manos
        for side in ["L", "R"]:
            # Cambia 'armIk_CTRL' por el sufijo exacto que use tu limbs_module.py para el control IK de la mano
            arm_ik_ctrl = f"{side}_Arm_armIk_CTRL"
            leg_ik_ctrl = f"{side}_Leg_legIk_CTRL"
            arm_pv_ctrl = f"{side}_Arm_poleVector_CTRL"
            leg_pv_ctrl = f"{side}_Leg_poleVector_CTRL"
            arm_fk_ctrl = f"{side}_Arm_shoulder_fk_CTRL"
            leg_fk_ctrl = f"{side}_Leg_thigh_fk_CTRL"
            
            
            
            if cmds.objExists(arm_ik_ctrl):
                hand_space_setup = spaceSwitching_module.SpaceModule(
                    target_control=arm_ik_ctrl,
                    space_dict={
                        "MasterWalk":  "Character_global_CTL",
                        "Chest":  "Character_chestFix_CTL",
                        "Body": "Character_body_CTL",
                        "Hip": "Character_localHip_CTL",
                        "Head": "Character_head_CTRL"
                    },
                    attr_name="Space_Switch",
                    rig_name="Character"
                )
                hand_space_setup.build()
                
            else:
                print(f"[Spaces] ADVERTENCIA: No se encontró el control {arm_ik_ctrl} en la escena.")
                
            if cmds.objExists(leg_ik_ctrl):
                leg_space_setup = spaceSwitching_module.SpaceModule(
                    target_control=leg_ik_ctrl,
                    space_dict={
                        "MasterWalk":  "Character_global_CTL",
                        "Body": "Character_body_CTL",
                        "Hip": "Character_localHip_CTL",
                    },
                    attr_name="Space_Switch",
                    rig_name="Character"
                )
                leg_space_setup.build()
                
            if cmds.objExists(arm_pv_ctrl):
                arm_pv_space_setup = spaceSwitching_module.SpaceModule(
                    target_control=arm_pv_ctrl,
                    space_dict={
                        "MasterWalk":  "Character_global_CTL",
                        "Body": "Character_body_CTL",
                        "Chest": "Character_chestFix_CTL",
                        "ArmIk": f"{side}_Arm_armIk_CTRL",
                        "Clavicule": f"{side}_Arm_clavicule_CTRL"
                    },
                    attr_name="Space_Switch",
                    rig_name="Character"
                )
                arm_pv_space_setup.build()
                
            if cmds.objExists(leg_pv_ctrl):
                leg_pv_space_setup = spaceSwitching_module.SpaceModule(
                    target_control=leg_pv_ctrl,
                    space_dict={
                        "MasterWalk":  "Character_global_CTL",
                        "Body": "Character_body_CTL",
                        "LegIk": f"{side}_Leg_legIk_CTRL"
                    },
                    attr_name="Space_Switch",
                    rig_name="Character"
                )
                leg_pv_space_setup.build()
                
            if cmds.objExists(arm_fk_ctrl):
                shoulder_space_setup = spaceSwitching_module.SpaceModule(
                    target_control=arm_fk_ctrl,
                    space_dict={
                        "Clavicule": f"{side}_Arm_clavicule_CTRL",
                        "Chest":  "Character_chestFix_CTL",
                        "Body": "Character_body_CTL"
                    },
                    attr_name="Space_Switch",
                    rig_name="Character"
                )
                shoulder_space_setup.build()
                
            if cmds.objExists(leg_fk_ctrl):
                thigh_space_setup = spaceSwitching_module.SpaceModule(
                    target_control=leg_fk_ctrl,
                    space_dict={
                        "MasterWalk":  "Character_global_CTL",
                        "Hip": "Character_localHip_CTL",
                        "Body": "Character_body_CTL"
                    },
                    attr_name="Space_Switch",
                    rig_name="Character"
                )
                thigh_space_setup.build()
                

        # =============================================================================
        # EJEMPLO DE USO — añadir en build_module.py justo después de self.neck_rig.build()
        # =============================================================================
        #
        #
        self.head_spaces = headSpace_module.HeadSpacesModule(
             rig_name         = "Character",
             head_ctrl        = "Character_head_CTRL",
             neck_ctrl        = "Character_neck_CTRL",
             chest_ctrl       = "Character_chestFix_CTL",
             body_ctrl        = "Character_body_CTL",
             master_walk_ctrl = "Character_global_CTL",
             root_instance    = self.root_rig,
         )
        self.head_spaces.build()