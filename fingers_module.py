import maya.cmds as cmds
import controlsLibrary
import groups_module  
 
class FingersModule(object):
 
    def __init__(self, wrist_guide="wrist", rig_name="Character",root_instance= None):
        self.wrist_guide = wrist_guide
        self.rig_name = rig_name
        self.styles = {"finger": "fingerControl"}
        self.group_maker = groups_module.ControlsGroups()
        
        self.joints_master_grp = None
        self.ctrls_master_grp = None
        self.root_instance = root_instance
                
    def get_finger_roots(self):
        return cmds.listRelatives(self.wrist_guide, c=True, type="joint") or []
 
    def build_finger_from_guides(self, guide_root):
        
 
        
        guide_chain = cmds.listRelatives(guide_root, ad=True, type="joint") or []
        guide_chain.append(guide_root)
        guide_chain.reverse()
 
        rig_chain = []
        cmds.select(clear=True)
 
        for guide in guide_chain:
            pos = cmds.xform(guide, q=True, ws=True, t=True)
            jnt_name = f"{self.rig_name}_{guide}_JNT"
            new_joint = cmds.joint(n=jnt_name, p=pos)
            rig_chain.append(new_joint)
 
        cmds.joint(rig_chain[0], e=True, oj="xyz", sao="yup", ch=True, zso=True)
        return rig_chain
 
    def create_finger_controls(self, rig_chain, bind_wrist):
        controls = []
        for i, jnt in enumerate(rig_chain[:-1]):
            ctrl_name = jnt.replace("_JNT", "_CTRL")
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["finger"], 
                final_name=ctrl_name
            )
            
            # Cambio aquí
            grp = self.group_maker.create_rig_hierarchy(ctrl, jnt)
            
            cmds.parentConstraint(ctrl, jnt, mo=True)
            
            if i == 0:
                if self.ctrls_master_grp:
                    cmds.parent(grp, self.ctrls_master_grp)
                if cmds.objExists(bind_wrist):
                    cmds.parentConstraint(bind_wrist, grp, mo=True)
            elif controls:
                cmds.parent(grp, controls[-1])
            controls.append(ctrl)
            
        
        return controls
 
    def build(self):
        # IMPORTANTE: El nombre debe coincidir con el creado en limbs_module
        #self.joints_master_grp = cmds.group(em=True, n=f"{self.rig_name}_Fingers_JNT_GRP")
        self.ctrls_master_grp = cmds.group(em=True, n=f"{self.rig_name}_Fingers_CTRL_GRP")
        
        # El nombre exacto que genera limbs_module: "{rig_name}_{names[3]}_bind_JNT"
        # Con rig_name="Arm_L" y names[3]="L_wrist" → "Arm_L_L_wrist_bind_JNT"
        side = "L" if self.rig_name.endswith("_L") or "_L_" in self.rig_name else "R"
        target_bind_wrist = f"{self.rig_name}_{side}_wrist_bind_JNT"
 
        print(f"Buscando muñeca de deformación: {target_bind_wrist}")
        finger_roots = self.get_finger_roots()
 
        for root in finger_roots:
            # 1. Crear joints del dedo
            rig_chain = self.build_finger_from_guides(root)
            
            # 2. EMPARENTAR JOINT: Primer joint del dedo debajo del bind wrist
            if cmds.objExists(target_bind_wrist):
                cmds.parent(rig_chain[0], target_bind_wrist)
            
            # 3. CREAR CONTROLES Y CONSTREÑIR AL WRIST
            self.create_finger_controls(rig_chain, target_bind_wrist)
            
        
        
        local_ctl = self.root_instance.localCtl if self.root_instance else None
        
        if local_ctl and cmds.objExists(local_ctl):
            cmds.parent(self.ctrls_master_grp, local_ctl) # Asegúrate de que el nombre del grupo sea el correcto
            print(f"DEBUG: Controles de dedos L emparentados a {local_ctl}")
        else:
            # Opcionalmente mandarlo al grupo de controles general
            global_controls_grp = f"{self.rig_name}_controls_GRP"
            if cmds.objExists(global_controls_grp):
                 cmds.parent(self.ctrls_master_grp, global_controls_grp)    

        print("Dedos vinculados y constreñidos al bind wrist.")
        print(f"Build {self.rig_name} completo.")
 
    # ------------------------------------------------------------------
    def build_mirror(self):
        """
        Construye los dedos del lado R. Los grupos viven bajo localCtl (world space limpio).
        """
        def to_r(name):
            return name.replace("L_", "R_", 1).replace("_L", "_R", 1)

        r_wrist_guide = to_r(self.wrist_guide)
        r_rig_name    = to_r(self.rig_name)

        if not cmds.objExists(r_wrist_guide):
            cmds.warning(f"build_mirror (fingers): no existe {r_wrist_guide}.")
            return None

        r_fingers = FingersModule(
            wrist_guide   = r_wrist_guide,
            rig_name      = r_rig_name,
            root_instance = self.root_instance
        )
        r_fingers.build()

        local_ctl = self.root_instance.localCtl if self.root_instance else None

        #if local_ctl and cmds.objExists(local_ctl):
            # Verificamos que el grupo de controles exista antes de emparentar
            #if r_fingers.ctrls_master_grp and cmds.objExists(r_fingers.ctrls_master_grp):
                #cmds.parent(r_fingers.ctrls_master_grp, local_ctl)
            
            # ELIMINAMOS O COMENTAMOS ESTO (es lo que causa el error porque joints_master_grp es None)
            # if cmds.objExists(r_fingers.joints_master_grp):
            #     cmds.parent(r_fingers.joints_master_grp, local_ctl)
            
            #print(f"build_mirror (fingers): {r_rig_name} emparentado a {local_ctl}")
        #else:
            #cmds.warning("build_mirror (fingers): no se encontro localCtl para emparentar.")

        return r_fingers