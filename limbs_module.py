import maya.cmds as cmds
import math
import controlsLibrary
import groups_module 
import rigRoot_module
import nodeCreator_module
import build_module
import rigRoot_module
import chest_module
from nodeCreator_module import NodeCreator
import twist_module

class LimbModule(object):
    """Módulo para construir los brazos, con setup IK/FK y switch."""

    def __init__(self, shoulder_guide="shoulder", 
                 elbow_guide="elbow", 
                 wrist_guide="wrist",
                 clavicule_guide="clavicule",
                 rig_name="Character",
                 root_instance=None,
                 side="L"):

        self.shoulder_guide  = shoulder_guide
        self.elbow_guide     = elbow_guide
        self.wrist_guide     = wrist_guide
        self.clavicule_guide = clavicule_guide
        
        self.side   = side
        self.prefix = f"{self.side}_{rig_name}"
        
        self.names  = ["clavicule", "shoulder", "elbow", "wrist"]
        self.rig_name = rig_name
        self.styles = {
            "mainIk":     "squareControl",
            "root":       "rootControl",
            "mainFk":     "circleControl",
            "switch":     "switchControl02",
            "poleVector": "poleVectorControl",
            "clavicule":  "claviculeControl"
        }
        
        self.group_maker = groups_module.ControlsGroups()
        self.root_instance = root_instance 
               
        self.ctrl_grp = None
        self.arm_grp  = None 
               
        self.orient           = "xyz" 
        self.secondary_orient = "yup"

        self.bind_chain = []
        self.ik_chain   = []
        self.fk_chain   = []


    def define_poleVector(self, shoulder, elbow, wrist, distance=15):
        """Calcula la posición del pole vector basándose en la posición de los joints."""
        sh_p = cmds.xform(shoulder, q=True, ws=True, t=True)
        el_p = cmds.xform(elbow,    q=True, ws=True, t=True)
        wr_p = cmds.xform(wrist,    q=True, ws=True, t=True)

        sw = [wr_p[i] - sh_p[i] for i in range(3)]
        se = [el_p[i] - sh_p[i] for i in range(3)]

        dot    = sum(se[i] * sw[i] for i in range(3))
        mag_sq = sum(sw[i] * sw[i] for i in range(3))

        if mag_sq < 0.0001:
            return el_p

        proj = [(dot / mag_sq) * sw[i] for i in range(3)]
        perp = [se[i] - proj[i] for i in range(3)]

        length = math.sqrt(sum(v * v for v in perp))
        if length < 0.0001:
            perp = [0, 0, 1]
        else:
            perp = [v / length for v in perp]

        return [el_p[i] + perp[i] * distance for i in range(3)]

        
    def build(self):
        """Construye el rig del brazo con setup IK/FK y switch."""

        # 1. POSICIONES REALES DE LAS GUIAS (para joints bind/ik/fk)
        pos_cl = cmds.xform(self.clavicule_guide, q=True, ws=True, t=True)
        pos_sh = cmds.xform(self.shoulder_guide,  q=True, ws=True, t=True)
        pos_el = cmds.xform(self.elbow_guide,     q=True, ws=True, t=True)
        pos_wr = cmds.xform(self.wrist_guide,     q=True, ws=True, t=True)


        # 1b. TARGETS PARA ALINEAR CONTROLES
        # Si es lado R, usamos las guías L para que el mirrorBehaviour_GRP
        # (scaleX -1) haga el mirror correcto, igual que en leg_module
        if self.side == "R":
            cl_ctrl_target = self.clavicule_guide.replace("R_", "L_")
            sh_ctrl_target = self.shoulder_guide.replace("R_", "L_")
            el_ctrl_target = self.elbow_guide.replace("R_", "L_")
            wr_ctrl_target = self.wrist_guide.replace("R_", "L_")
            sw_ctrl_target = self.shoulder_guide.replace("R_", "L_") 
        else:
            cl_ctrl_target = self.clavicule_guide
            sh_ctrl_target = self.shoulder_guide
            el_ctrl_target = self.elbow_guide
            wr_ctrl_target = self.wrist_guide
            sw_ctrl_target = self.shoulder_guide 
            

        # 2. BIND CHAIN (usa posiciones reales del lado correcto)
        cmds.select(clear=True)
        b_cl = cmds.joint(n=f"{self.prefix}_{self.names[0]}_bind_JNT", p=pos_cl)
        cmds.matchTransform(b_cl, self.clavicule_guide, rot=True, pos=False)
        
        cmds.select(clear=True)
        b_sh = cmds.joint(n=f"{self.prefix}_{self.names[1]}_bind_JNT", p=pos_sh)
        cmds.matchTransform(b_sh, self.shoulder_guide, rot=True, pos=False)
        
        cmds.select(clear=True)
        b_el = cmds.joint(n=f"{self.prefix}_{self.names[2]}_bind_JNT", p=pos_el)
        cmds.matchTransform(b_el, self.elbow_guide, rot=True, pos=False)
        
        cmds.select(clear=True)
        b_wr = cmds.joint(n=f"{self.prefix}_{self.names[3]}_bind_JNT", p=pos_wr)
        cmds.matchTransform(b_wr, self.wrist_guide, rot=True, pos=False)
        
        cmds.select(clear=True)
       
        cmds.parent(b_sh, b_cl)
        cmds.parent(b_el, b_sh)
        cmds.parent(b_wr, b_el)
        
        cmds.makeIdentity(b_cl, apply=True, t=0, r=1, s=0, n=0, pn=1)

        self.bind_chain = [b_sh, b_el, b_wr]
        self.b_cl = b_cl 
        
        def duplicate_chain(suffix):
            """Duplica la cadena de joints de bind y renombra con el sufijo dado."""
            new_jnts  = cmds.duplicate(self.bind_chain[0], rc=True)
            root      = cmds.rename(new_jnts[0], f"{self.prefix}_{self.names[1]}_{suffix}_JNT")
            children  = cmds.listRelatives(root, ad=True, type="joint")
            children.reverse()
            el = cmds.rename(children[0], f"{self.prefix}_{self.names[2]}_{suffix}_JNT")
            wr = cmds.rename(children[1], f"{self.prefix}_{self.names[3]}_{suffix}_JNT")
            return [root, el, wr]
            
        self.fk_chain = duplicate_chain("fk")
        self.ik_chain = duplicate_chain("ik")
        
        cmds.setAttr(f"{self.ik_chain[0]}.visibility",0)
        cmds.setAttr(f"{self.fk_chain[0]}.visibility",0)


        # 3. GRUPOS DE RIG
        self.main_rig_grp = cmds.group(em=True, n=f"{self.prefix}_armControls_GRP")
        self.main_grp     = self.main_rig_grp
        self.ik_grp       = cmds.group(em=True, n=f"{self.prefix}_ik_GRP",       p=self.main_rig_grp)
        self.fk_grp       = cmds.group(em=True, n=f"{self.prefix}_fk_GRP",       p=self.main_rig_grp)
        self.controls_grp = cmds.group(em=True, n=f"{self.prefix}_CONTROLS_GRP", p=self.main_rig_grp)
        self.arm_grp      = cmds.group(em=True, n=f"{self.prefix}_arm_GRP")
        
        # 4. IK SETUP
        pref_rot = 0.1 if self.side == "L" else -0.1
        cmds.setAttr(f"{self.ik_chain[1]}.rotateY", pref_rot) 
        cmds.joint(self.ik_chain[0], edit=True, ch=True, spa=True) 
        cmds.setAttr(f"{self.ik_chain[1]}.rotateY", 0) 

        ik_h, ik_eff = cmds.ikHandle(
            sj=self.ik_chain[0], ee=self.ik_chain[2],
            sol="ikRPsolver", n=f"{self.prefix}_IKH"
        )
        
        cmds.select(clear=True)
        cmds.parent(b_cl, self.arm_grp)
        
        # ---- CREAR CONTROLES (alineados con ctrl_targets) ----

        # Clavicule
        clavicule_ctl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["clavicule"], 
            final_name=f"{self.prefix}_clavicule_CTRL"
        )
        clav_gen = self.group_maker.create_rig_hierarchy(clavicule_ctl, cl_ctrl_target)

        # IK Root
        ik_root_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["root"], 
            final_name=f"{self.prefix}_armRoot_CTRL"
        )
        ik_root_gen = self.group_maker.create_rig_hierarchy(ik_root_ctrl, sh_ctrl_target)

        # IK Handle
        ik_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainIk"], 
            final_name=f"{self.prefix}_armIk_CTRL"
        )
        ik_ctrl_gen = self.group_maker.create_rig_hierarchy(ik_ctrl, wr_ctrl_target)

        # Pole Vector
        pv_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["poleVector"], 
            final_name=f"{self.prefix}_poleVector_CTRL"
        )
        pv_gen = self.group_maker.create_rig_hierarchy(pv_ctrl, self.ik_chain[1], world_space=False)

        # Switch
        switch_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["switch"], 
            final_name=f"{self.prefix}_switch_CTRL"
        )
        switch_gen = self.group_maker.create_rig_hierarchy(switch_ctrl, sw_ctrl_target)

        # FK alineados con sus propios joints (que ya están en R)
        fk_targets = [self.fk_chain[0], self.fk_chain[1], self.fk_chain[2]]
        fk_ctrls = []
        fk_gens  = []
        for i in range(3):
            ctrl_name = f"{self.prefix}_{self.names[i+1]}_fk_CTRL"
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"], 
                final_name=ctrl_name
            )
            gen = self.group_maker.create_rig_hierarchy(ctrl, fk_targets[i])
            fk_ctrls.append(ctrl)
            fk_gens.append(gen)
            
        
        cmds.parent(ik_root_gen, ik_ctrl_gen, pv_gen, self.ik_grp)
        cmds.parent(clav_gen, self.main_rig_grp)
        cmds.parent(switch_gen, self.main_rig_grp)


        cmds.matchTransform(clav_gen,    cl_ctrl_target)
        cmds.matchTransform(ik_root_gen, sh_ctrl_target)
        cmds.matchTransform(ik_ctrl_gen, wr_ctrl_target)
        cmds.matchTransform(switch_gen,  sw_ctrl_target)

        # Pole Vector
        pv_pos = self.define_poleVector(self.ik_chain[0], self.ik_chain[1], self.ik_chain[2], distance=15)
        cmds.xform(pv_gen, ws=True, t=pv_pos )
        if self.side == "R":
            cur_tx = cmds.getAttr(f"{pv_gen}.translateX")
            cmds.setAttr(f"{pv_gen}.translateX", -cur_tx)

        # AHORA sí meter en mirror, cuando ya están bien posicionados
        if self.side == "R":
            mirror_behavior_grp = f"{self.root_instance.rig_name}_mirrorBehaviour_GRP"
            if cmds.objExists(mirror_behavior_grp):
                cmds.parent(self.main_rig_grp, mirror_behavior_grp)
                cmds.setAttr(f"{self.main_rig_grp}.scaleX", 1)
                cmds.setAttr(f"{self.main_rig_grp}.scaleY", 1)
                cmds.setAttr(f"{self.main_rig_grp}.scaleZ", 1)
                cmds.setAttr(f"{self.main_rig_grp}.rotateX", 0)
                cmds.setAttr(f"{self.main_rig_grp}.rotateY", 0)
                cmds.setAttr(f"{self.main_rig_grp}.rotateZ", 0)
        
        # ---- CONEXIONES / CONSTRAINTS ----

        # Clavicule
        cmds.parentConstraint(clavicule_ctl, b_cl, mo=True)

        # IK Root
        cmds.pointConstraint(ik_root_ctrl, self.ik_chain[0], mo=True)

        # IK Handle
        cmds.orientConstraint(ik_ctrl, self.ik_chain[2], mo=True)

        # Pole Vector
        cmds.poleVectorConstraint(pv_ctrl, ik_h)


        # IK constraints
        cmds.parentConstraint(ik_ctrl, ik_h, mo=True)
        cmds.parentConstraint(clavicule_ctl, ik_root_gen, mo=True)
        cmds.parent(ik_h, self.arm_grp)

        # FK constraints y parenting
        for i in range(3):
            cmds.parentConstraint(fk_ctrls[i], self.fk_chain[i])
            if i == 0:
                cmds.parent(fk_gens[i], self.fk_grp)
            else:
                cmds.parent(fk_gens[i], fk_ctrls[i-1])

        cmds.parentConstraint(clavicule_ctl, self.fk_grp, mo=True)

        # Switch
        cmds.xform(switch_gen, r=True, os=True, t=(0, 10, 0)) 
        cmds.parentConstraint(clavicule_ctl, switch_gen, mo = True)
        cmds.addAttr(switch_ctrl, ln="IK_FK", at="double", min=0, max=1,dv = 1, k=True)

        # 6. SWITCH & VISIBILIDAD
        vis_rev = cmds.createNode("reverse", n=f"{self.prefix}_VIS_REV")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{vis_rev}.inputX")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{self.fk_grp}.visibility")
        cmds.connectAttr(f"{vis_rev}.outputX",   f"{self.ik_grp}.visibility")
        
        # 7. BLEND (Pair Blends)
        for i in range(len(self.bind_chain)):
            bnd_jnt = self.bind_chain[i]
            ik_jnt  = self.ik_chain[i]
            fk_jnt  = self.fk_chain[i]

            pbl_creator = NodeCreator(
                side=self.side,   
                node_type="pairBlend",
                base_name=self.prefix,              
                name=self.names[i+1],                   
                tag="blend",
                parent=None,
                custom_suffix=None                    
            )
            pbl = pbl_creator.create()
            
            cmds.setAttr(f"{pbl}.rotInterpolation", 1) 

            cmds.connectAttr(f"{ik_jnt}.translate",  f"{pbl}.inTranslate1")
            cmds.connectAttr(f"{ik_jnt}.rotate",     f"{pbl}.inRotate1")
            cmds.connectAttr(f"{fk_jnt}.translate",  f"{pbl}.inTranslate2")
            cmds.connectAttr(f"{fk_jnt}.rotate",     f"{pbl}.inRotate2")
            cmds.connectAttr(f"{pbl}.outTranslate",  f"{bnd_jnt}.translate")
            cmds.connectAttr(f"{pbl}.outRotate",     f"{bnd_jnt}.rotate")
            cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{pbl}.weight")
            
        # =====================================================================
        # 7.5 SISTEMA DE TWIST
        # =====================================================================

        shoulder_jnt = self.bind_chain[0]  
        elbow_jnt    = self.bind_chain[1]  
        wrist_jnt    = self.bind_chain[2]  

        arm_twist = twist_module.TwistModule(name="arm", side=self.side)

        creaciones_twist = arm_twist.create_basic_curve(shoulder_jnt, elbow_jnt, wrist_jnt)
        

                        
                            
        # 8. ORGANIZACIÓN FINAL
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.arm_grp, rig_grp)
            
        local_ctl = self.root_instance.localCtl if self.root_instance else None
        if local_ctl and cmds.objExists(local_ctl):
            if self.side == "L":
                cmds.parent(self.main_rig_grp, local_ctl)

        # Cambia las últimas líneas de limbs_module.py por esto:
        chestControl = "Character_chestFix_CTL"
        
        if cmds.objExists(chestControl):
            # Es mejor restringir el grupo de la clavícula manteniendo el offset
            cmds.parentConstraint(chestControl, clav_gen, mo=True)
            print(f"Conectada la clavícula {self.prefix} al pecho con éxito.")
        else:
            # Si entra aquí, es porque el pecho no se ha creado todavía en la escena
            print(f"ADVERTENCIA: No se pudo encontrar {chestControl}. Asegúrate de construir el ChestModule ANTES que los Limbs.")

        print(f"Build {self.prefix} completo.")