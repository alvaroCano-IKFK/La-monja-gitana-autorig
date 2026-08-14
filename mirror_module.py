import maya.cmds as cmds

class Mirror(object):
    def __init__(self, clavicule_guide="L_clavicule", thigh_guide="L_hip", lip_end="L_lip_end",
                eye_mid="L_eye_mid", eye_inner_corner="L_eye_inner_corner", eye_outer_corner="L_eye_outer_corner",
                eyelid_up="L_eyelid_up", eyelid_low="L_eyelid_low",
                eyelid_up02="L_eyelid_up02", eyelid_up03="L_eyelid_up03",
                eyelid_low02="L_eyelid_low02", eyelid_low03="L_eyelid_low03",
                rig_name="R_Character"):
        
        self.clavicule_guide = clavicule_guide
        self.thigh_guide = thigh_guide
        self.lip_end = lip_end
        self.eye_mid = eye_mid
        self.eye_inner_corner = eye_inner_corner
        self.eye_outer_corner = eye_outer_corner
        self.eyelid_up = eyelid_up
        self.eyelid_low = eyelid_low
        self.eyelid_up02 = eyelid_up02
        self.eyelid_up03 = eyelid_up03
        self.eyelid_low02 = eyelid_low02
        self.eyelid_low03 = eyelid_low03
        self.rig_name = rig_name
        
        # Variables para guardar los nombres de los joints creados
        self.r_clavicule = None
        self.r_hip = None
        self.r_lip_end = None
        self.r_eye_mid = None
        self.r_eye_inner_corner = None
        self.r_eye_outer_corner = None
        self.r_eyelid_up = None
        self.r_eyelid_low = None
        self.r_eyelid_up02 = None
        self.r_eyelid_up03 = None
        self.r_eyelid_low02 = None
        self.r_eyelid_low03 = None
        
    def mirror(self):
        # mirrorJoint devuelve una lista. El primer elemento [0] es la raíz duplicada.
        if cmds.objExists(self.clavicule_guide):
            res_arm = cmds.mirrorJoint(self.clavicule_guide, myz=True, mb=True, sr=("L", "R"))
            self.r_clavicule = res_arm[0]
        
        if cmds.objExists(self.thigh_guide):
            res_leg = cmds.mirrorJoint(self.thigh_guide, myz=True, mb=True, sr=("L", "R"))
            self.r_hip = res_leg[0]
        
        if cmds.objExists(self.lip_end):
            res_lip = cmds.mirrorJoint(self.lip_end, myz=True, mb=True, sr=("L", "R"))
            self.r_lip_end = res_lip[0] 
        else:
            cmds.warning(f"[Mirror] No se encontró {self.lip_end} en la escena, no se puede mirrorizar la boca.")

        # Las tres joints del ojo son independientes (el group las separó), así que se mirrorizan una a una.
        if cmds.objExists(self.eye_mid):
            res_eye = cmds.mirrorJoint(self.eye_mid, myz=True, mb=True, sr=("L", "R"))
            self.r_eye_mid = res_eye[0]
        else:
            cmds.warning(f"[Mirror] No se encontró {self.eye_mid} en la escena, no se puede mirrorizar el ojo.")

        if cmds.objExists(self.eye_inner_corner):
            res_eye_in = cmds.mirrorJoint(self.eye_inner_corner, myz=True, mb=True, sr=("L", "R"))
            self.r_eye_inner_corner = res_eye_in[0]
        else:
            cmds.warning(f"[Mirror] No se encontró {self.eye_inner_corner} en la escena, no se puede mirrorizar la esquina interna del ojo.")

        if cmds.objExists(self.eye_outer_corner):
            res_eye_out = cmds.mirrorJoint(self.eye_outer_corner, myz=True, mb=True, sr=("L", "R"))
            self.r_eye_outer_corner = res_eye_out[0]
        else:
            cmds.warning(f"[Mirror] No se encontró {self.eye_outer_corner} en la escena, no se puede mirrorizar la esquina externa del ojo.")

        if cmds.objExists(self.eyelid_up):
            res_eyelid_up = cmds.mirrorJoint(self.eyelid_up, myz=True, mb=True, sr=("L", "R"))
            self.r_eyelid_up = res_eyelid_up[0]
        else:
            cmds.warning(f"[Mirror] No se encontró {self.eyelid_up} en la escena, no se puede mirrorizar el párpado superior.")

        if cmds.objExists(self.eyelid_low):
            res_eyelid_low = cmds.mirrorJoint(self.eyelid_low, myz=True, mb=True, sr=("L", "R"))
            self.r_eyelid_low = res_eyelid_low[0]
        else:
            cmds.warning(f"[Mirror] No se encontró {self.eyelid_low} en la escena, no se puede mirrorizar el párpado inferior.")
            
        if cmds.objExists(self.eyelid_up02):
            res_eyelid_up02 = cmds.mirrorJoint(self.eyelid_up02, myz=True, mb=True, sr=("L", "R"))
            self.r_eyelid_up02 = res_eyelid_up02[0]
        else:
            cmds.warning(f"[Mirror] No se encontró {self.eyelid_up02} en la escena, no se puede mirrorizar el párpado superior 02.")
        
        if cmds.objExists(self.eyelid_up03):
            res_eyelid_up03 = cmds.mirrorJoint(self.eyelid_up03, myz=True, mb=True, sr=("L", "R"))
            self.r_eyelid_up03 = res_eyelid_up03[0]
        else:
            cmds.warning(f"[Mirror] No se encontró {self.eyelid_up03} en la escena, no se puede mirrorizar el párpado superior 03.")
        
        if cmds.objExists(self.eyelid_low02):
            res_eyelid_low02 = cmds.mirrorJoint(self.eyelid_low02, myz=True, mb=True, sr=("L", "R"))
            self.r_eyelid_low02 = res_eyelid_low02[0]
        else:
            cmds.warning(f"[Mirror] No se encontró {self.eyelid_low02} en la escena, no se puede mirrorizar el párpado inferior 02.")
        
        if cmds.objExists(self.eyelid_low03):
            res_eyelid_low03 = cmds.mirrorJoint(self.eyelid_low03, myz=True, mb=True, sr=("L", "R"))
            self.r_eyelid_low03 = res_eyelid_low03[0]
        else:
            cmds.warning(f"[Mirror] No se encontró {self.eyelid_low03} en la escena, no se puede mirrorizar el párpado inferior 03.")
            
            