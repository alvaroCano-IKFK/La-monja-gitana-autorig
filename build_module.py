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
import body_module
import spaceSwitching_module
import headSpace_module
import curvature_module
import soft_module
import pvPin_module
import mouthModule
import jaw_module
import eyes_module
import progress_module



class BuildRig(object):

    # Numero de llamadas a prog.step() que hay en _build_steps().
    # Si anades o quitas pasos, actualiza este numero o la barra se
    # quedara corta / larga.
    TOTAL_STEPS = 23

    def build(self, show_progress=True):
        """
        Metodo que llama el boton BUILD de la UI.
        Solo se encarga de abrir la barra de progreso y delegar el trabajo
        real en _build_steps(). Asi la logica de construccion sigue limpia.
        """
        print("Iniciando construcción del Rig...")

        if not show_progress:
            # Modo silencioso: util para tests o para lanzarlo en batch.
            prog = progress_module.RigProgress(total=self.TOTAL_STEPS)
            prog.enabled = False
            return self._build_steps(prog)

        with progress_module.rig_progress(
                title="La monja gitana autorig",
                total=self.TOTAL_STEPS,
                mode="window") as prog:
            self._build_steps(prog)

        print("Rig construido.")

    def _build_steps(self, prog):
        """Construccion real del rig. 'prog' es la barra de progreso."""
        #Llista amb tots els grups de guies creats       
    
        # 0. CONSTRUIR ROOT RIG (NUEVO - va primero)
        prog.step("Root rig")
        self.root_rig = rigRoot_module.RigRoot(rig_name="Character")
        self.root_rig.build()
        #self.root_rig.mirrorControls()

        # 0. CONSTRUIR BODY
        prog.step("Body")
        self.body_rig = body_module.BodyModule(
                rig_name="Character",
                root_instance=self.root_rig
            )    
        self.body_rig.build()   


        # 1. CONSTRUIR ESPINA
        prog.step("Espina")
        self.spine_rig = spine_module.SpineModule(
                root_guide="root", 
                chest_guide="chest", 
                rig_name="Character",
                root_instance=self.root_rig
            )
        self.spine_rig.build()

        #CONSTRUIR CHEST
            
        prog.step("Chest")
        self.chest_rig = chest_module.ChestModule(chest_guide = "chest",root_instance=self.root_rig)
            
        self.chest_rig.build()   

        # 2. CONSTRUIR BRAZO (Aquí estaba el fallo, faltaba llamar al módulo)
        prog.step("Brazo izquierdo")
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
        
        prog.step("Brazo derecho")
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
        prog.step("Dedos izquierda")
        self.fingers_rig = fingers_module.FingersModule( 
                wrist_guide="L_wrist", 
                rig_name ="Arm",
                side = "L",
                root_instance=self.root_rig)
        self.fingers_rig.build()
        
        prog.step("Dedos derecha")
        self.mirror_fingers_rig = fingers_module.FingersModule(
                wrist_guide="R_wrist",
                rig_name="Arm",
                side="R",
                root_instance=self.root_rig)
        self.mirror_fingers_rig.build()
            
        # Modifica LimbModule para que guarde self.b_sh al terminar build.
        shoulder_jnt = "L_Arm_shoulder_bind_JNT"
            
        # CONSTRUIR CUELLO
        prog.step("Cuello")
        self.neck_rig = neck_module.NeckModule(
                neck_root="neck_root", 
                neck_end="neck_end", 
                rig_name="Character",
                root_instance=self.root_rig
            )
        self.neck_rig.build()
            
        #CONSTRRUIR HIP
            
        prog.step("Hip")
        self.hip_rig = hip_module.HipModule(root_guide ="root",root_instance=self.root_rig)
            
        self.hip_rig.build()
            

        # En el método build de CharacterGuides
        prog.step("Pierna izquierda")
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

        prog.step("Pierna derecha")
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

        prog.step("Boca izquierda")
        self.mouth_rig = mouthModule.MouthModule(
                boca_surface="boca_surface",
                lip_mid="C_lip_mid",
                lip_end="L_lip_end",
                root_instance=self.root_rig,
                rig_name="Character",
                side="L"
            )
        self.mouth_rig.build()
        
        prog.step("Boca derecha")
        self.mirror_mouth_rig = mouthModule.MouthModule(
                boca_surface="boca_surface",
                lip_mid="C_lip_mid",
                lip_end="R_lip_end",
                root_instance=self.root_rig,
                rig_name="Character",
                side="R"
            )
        self.mirror_mouth_rig.build()
        
        prog.step("Mandibula")
        self.jaw_rig = jaw_module.JawModule(
                jaw_root="jaw_root",
                jaw_end="jaw_end",
                root_instance=self.root_rig,
                rig_name="Character",
                side="C"
            )
        self.jaw_rig.build()
        
        prog.step("Ojos izquierda")
        self.eyes_rig = eyes_module.EyesModule(
                root_instance=self.root_rig,
                rig_name="Character",
                side="L"
            )
        self.eyes_rig.build()

        prog.step("Ojos derecha")
        self.mirror_eyes_rig = eyes_module.EyesModule(
                root_instance=self.root_rig,
                rig_name="Character",
                side="R"
            )
        self.mirror_eyes_rig.build()

        # Importamos el módulo de skinning
        prog.step("Skinning")
        skn = skinning_module.SkinningModule(
                rig_name="Character",
                root_instance=self.root_rig
            )
        skn.build()
        
        prog.step("Soft IK piernas")
        soft_leg_L = soft_module.SoftIkModule(side="L", prefix="Leg")
        soft_leg_L_result = soft_leg_L.apply_soft_ik(
            ik_ctrl="L_Leg_legIk_CTRL",
            ik_handle="L_Leg_IKH",
            root_ctrl="L_Leg_legRoot_CTRL",
            mid_jnt="L_Leg_knee_ik_JNT",
            low_jnt="L_Leg_ankle_ik_JNT",
            global_ctrl="Character_global_CTL",
            ik_hdl="L_Leg_IKH",
            root_jnt="L_Leg_thigh_ik_JNT",
            goal_ctrl="L_Leg_footBall_CTRL"
        )

        soft_leg_R = soft_module.SoftIkModule(side="R", prefix="Leg")
        soft_leg_R_result = soft_leg_R.apply_soft_ik(
            ik_ctrl="R_Leg_legIk_CTRL",
            ik_handle="R_Leg_IKH",
            root_ctrl="R_Leg_legRoot_CTRL",
            mid_jnt="R_Leg_knee_ik_JNT",
            low_jnt="R_Leg_ankle_ik_JNT",
            global_ctrl="Character_global_CTL",
            ik_hdl="R_Leg_IKH",
            root_jnt="R_Leg_thigh_ik_JNT",
            goal_ctrl="R_Leg_footBall_CTRL"
        )

        prog.step("Soft IK brazos")
        soft_arm_L = soft_module.SoftIkModule(side="L", prefix="Arm")
        soft_arm_L_result = soft_arm_L.apply_soft_ik(
            ik_ctrl="L_Arm_armIk_CTRL",
            ik_handle="L_Arm_IKH",
            root_ctrl="L_Arm_armRoot_CTRL",
            mid_jnt="L_Arm_elbow_ik_JNT",
            low_jnt="L_Arm_wrist_ik_JNT",
            global_ctrl="Character_global_CTL",
            ik_hdl="L_Arm_IKH",
            root_jnt="L_Arm_shoulder_ik_JNT"
        )

        soft_arm_R = soft_module.SoftIkModule(side="R", prefix="Arm")
        soft_arm_R_result = soft_arm_R.apply_soft_ik(
            ik_ctrl="R_Arm_armIk_CTRL",
            ik_handle="R_Arm_IKH",
            root_ctrl="R_Arm_armRoot_CTRL",
            mid_jnt="R_Arm_elbow_ik_JNT",
            low_jnt="R_Arm_wrist_ik_JNT",
            global_ctrl="Character_global_CTL",
            ik_hdl="R_Arm_IKH",
            root_jnt="R_Arm_shoulder_ik_JNT"
        )     
        
        #========================================================================
        #PV PIN
        #========================================================================
        prog.step("Pole vector pins")
        pv_pin_L = pvPin_module.Pv_pin(side="L", name="Arm")
        pv_pin_leg_L = pvPin_module.Pv_pin(side="L", name="leg")
        pv_pin_leg_L.setup_pole_vector_pin(
            ik_control="L_Leg_legIk_CTRL",
            root_control="L_Leg_legRoot_CTRL",
            pole_vector_control="L_Leg_poleVector_CTRL",
            soft_trn=soft_leg_L_result["softTransform_node"],
            soft_condition_node=soft_leg_L_result["condition_node"],
            upper_ik_joint="L_Leg_knee_ik_JNT",
            lower_ik_joint="L_Leg_ankle_ik_JNT"
        )

        pv_pin_leg_R = pvPin_module.Pv_pin(side="R", name="leg")
        pv_pin_leg_R.setup_pole_vector_pin(
            ik_control="R_Leg_legIk_CTRL",
            root_control="R_Leg_legRoot_CTRL",
            pole_vector_control="R_Leg_poleVector_CTRL",
            soft_trn=soft_leg_R_result["softTransform_node"],
            soft_condition_node=soft_leg_R_result["condition_node"],
            upper_ik_joint="R_Leg_knee_ik_JNT",
            lower_ik_joint="R_Leg_ankle_ik_JNT"
        )

        pv_pin_arm_L = pvPin_module.Pv_pin(side="L", name="arm")
        pv_pin_arm_L.setup_pole_vector_pin(
            ik_control="L_Arm_armIk_CTRL",
            root_control="L_Arm_armRoot_CTRL",
            pole_vector_control="L_Arm_poleVector_CTRL",
            soft_trn=soft_arm_L_result["softTransform_node"],
            soft_condition_node=soft_arm_L_result["condition_node"],
            upper_ik_joint="L_Arm_elbow_ik_JNT",
            lower_ik_joint="L_Arm_wrist_ik_JNT"
        )

        pv_pin_arm_R = pvPin_module.Pv_pin(side="R", name="arm")
        pv_pin_arm_R.setup_pole_vector_pin(
            ik_control="R_Arm_armIk_CTRL",
            root_control="R_Arm_armRoot_CTRL",
            pole_vector_control="R_Arm_poleVector_CTRL",
            soft_trn=soft_arm_R_result["softTransform_node"],
            soft_condition_node=soft_arm_R_result["condition_node"],
            upper_ik_joint="R_Arm_elbow_ik_JNT",
            lower_ik_joint="R_Arm_wrist_ik_JNT"
        )

        # =========================================================================
        # CONFIGURACIÓN DE SPACES (DYNAMIC PARENTS) - ANTES DEL SKINNING
        # =========================================================================
        prog.step("Space switching")
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
        prog.step("Head spaces")
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