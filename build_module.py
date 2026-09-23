import maya.cmds as cmds
from functools import partial 
import os
import math
import json
import horse_spine
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
import back_legs_module
import horse_neck



class BuildRig(object):
    
    def build(self):
        """Este es el método que llama el botón BUILD de la UI"""
        print("Iniciando construcción del Rig...")
        #Llista amb tots els grups de guies creats       
    
        # 0. CONSTRUIR ROOT RIG (NUEVO - va primero)
        self.root_rig = rigRoot_module.RigRoot(rig_name="Character")
        self.root_rig.build()
        #self.root_rig.mirrorControls()

        # 0. HIP + BODY (COG amb pivot movible)
        #    Va abans de l espina perque els seus controls pengen del body_CTL
        self.body_rig = None
        self.hip_rig = hip_module.HipModule(
                root_guide="spine_root",
                rig_name="Character",
                root_instance=self.root_rig
            )
        self.hip_rig.build()


        # 1. CONSTRUIR ESPINA (quadrupede)
        # Els controls pengen del body_CTL (fa de COG) i els joints van al rig_GRP
        self.spine_rig = horse_spine.HorseSpine(
                name="Character_spine",
                num_joints=9,
                guide_names=("spine_root", "spine_end"),
                root_instance=self.root_rig
            )
        self.spine_data = self.spine_rig.build()

        # Joints de l espina on s enganxen les cames. Es fan servir els joints
        # (i no els controls) perque segueixen l esquelet real encara que
        # l stretch estigui apagat.
        self.spine_chest = self.spine_data["chest_jnt"]   # cames de davant
        self.spine_pelvis = self.spine_data["pelvis"]     # pates del darrere

        # 2. CONSTRUIR COLL (ribbon NURBS + uvPin, 3 controls).
        #    La base segueix el pit de l espina
        self.horse_neck_rig = horse_neck.HorseNeck(
                root_guide="neck_root",
                mid_guide="neck_mid",
                end_guide="neck_end",
                rig_name="Character",
                v_patches=10,
                u_patches=2,
                parent_joint=self.spine_chest,
                root_instance=self.root_rig
            )
        self.horse_neck_rig.build()

        # ---------------------------------------------------------------
        # CHEST / NECK / HIP DEL BIPED: DESACTIVATS PER AL QUADRUPEDE
        # Depenen de l espina vella (Character_spine_3_JNT, spine_4_CTL,
        # spine_IK). La HorseSpine ja fa de pit i pelvis, i les cames
        # s enganxen directament als seus joints.
        # ---------------------------------------------------------------
        self.chest_rig = None
        self.neck_rig = None

        # #CONSTRUIR CHEST
            
        # self.chest_rig = chest_module.ChestModule(chest_guide = "chest",root_instance=self.root_rig)
            
        # self.chest_rig.build()
        # self.root_rig.chest_instance = self.chest_rig   



            
        # # Modifica LimbModule para que guarde self.b_sh al terminar build.
        # shoulder_jnt = "L_Arm_shoulder_bind_JNT"
            
        # # CONSTRUIR CUELLO
        # self.neck_rig = neck_module.NeckModule(
        #         neck_root="neck_root", 
        #         neck_end="neck_end", 
        #         rig_name="Character",
        #         root_instance=self.root_rig
        #     )
        # self.neck_rig.build()
            
        # #CONSTRRUIR HIP
            
        # self.hip_rig = hip_module.HipModule(root_guide ="root",root_instance=self.root_rig)
            
        # self.hip_rig.build()

        # # ENGANXAR CHEST I HIP A L ESPINA
        # # chestFix_CTL i localHip_CTL queden com a controls locals per sobre
        # # dels drivers de l espina (i les cames, que hi pengen, la segueixen)
        # spine_ctrls = self.spine_data["controls"]
        # self.spine_rig.attach_control(spine_ctrls["chest"]["ctrl"], "Character_chestFix_CTL")
        # self.spine_rig.attach_control(spine_ctrls["hip"]["ctrl"], "Character_localHip_CTL")
            

        # =========================================================================
        # CAMES DE DAVANT I PATES DEL DARRERE (amb casc)
        # =========================================================================
        # Mateix LegModule per a les quatre potes, amb hoof=True.
        #   davant:   escapula  -> pit de l espina,    guies sense sufix
        #   darrere:  legRoot   -> pelvis de l espina, guies amb sufix _back
        leg_setups = [
            # DAVANT: escapula flotant, IK de 2 segments
            {"rig_name": "Leg", "suffix": "", "spine_parent": self.spine_chest,
             "clavicle": True, "scapula": True, "three_bone": False},
            # DARRERE: sense clavicula (pelvis de l espina), IK spring de 3 segments
            {"rig_name": "BackLeg", "suffix": "_back", "spine_parent": self.spine_pelvis,
             "clavicle": False, "scapula": False, "three_bone": True},
        ]

        self.leg_rigs = {}
        for setup in leg_setups:
            rig_name = setup["rig_name"]
            keys = ["hip", "knee", "ankle", "ball", "toe_tip", "heel", "hoof_in", "hoof_out"]
            if setup["clavicle"]:
                keys += ["clavicule_start", "clavicule"]
            if setup["three_bone"]:
                keys += ["hock"]

            for side in ["L", "R"]:
                guides = {k: f"{side}_{k}{setup['suffix']}" for k in keys}
                missing = [gd for gd in guides.values() if not cmds.objExists(gd)]
                if missing:
                    cmds.warning(f"[{rig_name}] Falten guies del costat {side}: {missing}. "
                                 f"Torna a crear les guies (i MIRROR). S ignora {side}_{rig_name}.")
                    continue

                leg_rig = leg_module.LegModule(
                        clavicule_start_guide=guides.get("clavicule_start"),
                        clavicule_guide=guides.get("clavicule"),
                        thigh_guide=guides["hip"],
                        knee_guide=guides["knee"],
                        ankle_guide=guides["ankle"],
                        ball_guide=guides["ball"],
                        tip_guide=guides["toe_tip"],
                        heel_guide=guides["heel"],
                        rig_name=rig_name,
                        side=side,
                        root_instance=self.root_rig,
                        hip_instance=None,
                        clavicule_parent=setup["spine_parent"],
                        hoof=True,
                        bank_in_guide=guides["hoof_in"],
                        bank_out_guide=guides["hoof_out"],
                        scapula=setup["scapula"],
                        clavicle=setup["clavicle"],
                        three_bone=setup["three_bone"],
                        hock_guide=guides.get("hock")
                    )
                leg_rig.build()
                self.leg_rigs[f"{side}_{rig_name}"] = leg_rig

        # Noms antics per si algun altre modul els fa servir
        self.leg_rig = self.leg_rigs.get("L_Leg")
        self.mirror_leg_rig = self.leg_rigs.get("R_Leg")
        self.back_leg_rigs = [self.leg_rigs[k] for k in ("L_BackLeg", "R_BackLeg")
                              if k in self.leg_rigs]


        # Importamos el módulo de skinning
        skn = skinning_module.SkinningModule(
                rig_name="Character",
                root_instance=self.root_rig
            )
        skn.build()
                        
        

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
            back_leg_ik_ctrl = f"{side}_BackLeg_legIk_CTRL"
            back_leg_pv_ctrl = f"{side}_BackLeg_poleVector_CTRL"
            back_leg_fk_ctrl = f"{side}_BackLeg_thigh_fk_CTRL"
            
            
            
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
                        "Chest": self.spine_chest,
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
                        "Chest": self.spine_chest,
                        "Body": "Character_body_CTL"
                    },
                    attr_name="Space_Switch",
                    rig_name="Character"
                )
                thigh_space_setup.build()

            # Spaces de les pates del darrere (mateixos que la cama de davant)
            if cmds.objExists(back_leg_ik_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=back_leg_ik_ctrl,
                    space_dict={
                        "MasterWalk":  "Character_global_CTL",
                        "Body": "Character_body_CTL",
                        "Hip": self.spine_pelvis,
                    },
                    attr_name="Space_Switch",
                    rig_name="Character"
                ).build()

            if cmds.objExists(back_leg_pv_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=back_leg_pv_ctrl,
                    space_dict={
                        "MasterWalk":  "Character_global_CTL",
                        "Body": "Character_body_CTL",
                        "LegIk": back_leg_ik_ctrl
                    },
                    attr_name="Space_Switch",
                    rig_name="Character"
                ).build()

            if cmds.objExists(back_leg_fk_ctrl):
                spaceSwitching_module.SpaceModule(
                    target_control=back_leg_fk_ctrl,
                    space_dict={
                        "MasterWalk":  "Character_global_CTL",
                        "Hip": self.spine_pelvis,
                        "Body": "Character_body_CTL"
                    },
                    attr_name="Space_Switch",
                    rig_name="Character"
                ).build()
                

        # =============================================================================
        # EJEMPLO DE USO — añadir en build_module.py justo después de self.neck_rig.build()
        # =============================================================================
        #
        #
        # Desactivat: depen del neck i el chest del biped
        # self.head_spaces = headSpace_module.HeadSpacesModule(
        #      rig_name         = "Character",
        #      head_ctrl        = "Character_head_CTRL",
        #      neck_ctrl        = "Character_neck_CTRL",
        #      chest_ctrl       = "Character_chestFix_CTL",
        #      body_ctrl        = "Character_body_CTL",
        #      master_walk_ctrl = "Character_global_CTL",
        #      root_instance    = self.root_rig,
        #  )
        # self.head_spaces.build()