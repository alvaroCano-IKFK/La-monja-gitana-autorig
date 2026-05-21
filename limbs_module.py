import maya.cmds as cmds
import math
import controlsLibrary
import groups_module 
import rigRoot_module
import nodeCreator_module
import build_module
from nodeCreator_module import NodeCreator

class LimbModule(object):

    def __init__(self, shoulder_guide="shoulder", 
                 elbow_guide="elbow", 
                 wrist_guide="wrist",
                 clavicule_guide ="clavicule",
                 rig_name="Character",
                 root_instance= None):
                     
        self.shoulder_guide = shoulder_guide
        self.elbow_guide = elbow_guide
        self.wrist_guide = wrist_guide
        self.clavicule_guide= clavicule_guide
        self.names = ["clavicule","shoulder","elbow","wrist"]
        self.rig_name = rig_name
        self.styles = {"mainIk": "squareControl",
                              "root": "rootControl",
                              "mainFk": "circleControl",
                              "switch": "switchControl02",
                              "poleVector": "poleVectorControl",
                              "clavicule": "claviculeControl"}
        
        self.group_maker = groups_module.ControlsGroups()
        
        #grupo del root rig
        self.root_instance = root_instance 
               
        self.ctrl_grp =None
        self.arm_grp = None 
               
        
        self.orient = "xyz" 
        self.secondary_orient = "yup"

        self.bind_chain = []
        self.ik_chain = []
        self.fk_chain = []


    #def define_poleVector(self, shoulder, elbow, wrist, distance=5):
    def define_poleVector(self, shoulder, elbow, wrist, distance=5):
        # 1. Obtener posiciones en World Space
        sh_p = cmds.xform(shoulder, q=True, ws=True, t=True)
        el_p = cmds.xform(elbow, q=True, ws=True, t=True)
        wr_p = cmds.xform(wrist, q=True, ws=True, t=True)

        # 2. Crear vectores (Muñeca - Hombro) y (Codo - Hombro)
        sw = [wr_p[0] - sh_p[0], wr_p[1] - sh_p[1], wr_p[2] - sh_p[2]]
        se = [el_p[0] - sh_p[0], el_p[1] - sh_p[1], el_p[2] - sh_p[2]]

        # 3. Proyección de 'se' sobre 'sw'
        # Fórmula: (a · b / |b|^2) * b
        dot = sum(se[i] * sw[i] for i in range(3))
        mag_sq = sum(sw[i] * sw[i] for i in range(3))

        if mag_sq < 0.0001: # Evitar división por cero
            return el_p

        proj = [(dot / mag_sq) * sw[i] for i in range(3)]
        
        # 4. Vector perpendicular (desde la proyección hacia el codo)
        perp = [se[i] - proj[i] for i in range(3)]

        # 5. Normalizar el vector perpendicular y aplicar distancia
        length = math.sqrt(sum(v * v for v in perp))
        if length < 0.0001:
            perp = [0, 0, 1] # Dirección por defecto si el brazo está recto
        else:
            perp = [v / length for v in perp]

        # 6. Posición final
        return [
            el_p[0] + perp[0] * distance,
            el_p[1] + perp[1] * distance,
            el_p[2] + perp[2] * distance
        ]
        
def build(self):
        # Detectamos el lado según el rig_name (ej: "Arm_L" -> "L", "Arm_R" -> "R")
        side = "L"
        if self.rig_name.endswith("_R") or "_R_" in self.rig_name:
            side = "R"
         
        # 1. OBTENER POSICIONES ABSOLUTAS DESDE LAS GUIAS
        pos_cl = cmds.xform(self.clavicule_guide, q=True, ws=True, t=True)
        pos_sh = cmds.xform(self.shoulder_guide, q=True, ws=True, t=True)
        pos_el = cmds.xform(self.elbow_guide, q=True, ws=True, t=True)
        pos_wr = cmds.xform(self.wrist_guide, q=True, ws=True, t=True)

        # 2. CREACIÓN DE LA CADENA BIND
        cmds.select(clear=True)
        b_cl = cmds.joint(n=f"{self.rig_name}_{self.names[0]}_bind_JNT", p=pos_cl)
        cmds.select(clear=True)
        b_sh = cmds.joint(n=f"{self.rig_name}_{self.names[1]}_bind_JNT", p=pos_sh)
        cmds.select(clear=True)
        b_el = cmds.joint(n=f"{self.rig_name}_{self.names[2]}_bind_JNT", p=pos_el)
        cmds.select(clear=True)
        b_wr = cmds.joint(n=f"{self.rig_name}_{self.names[3]}_bind_JNT", p=pos_wr)
        cmds.select(clear=True)
       
        # Estructurar jerarquía básica de joints
        cmds.parent(b_sh, b_cl)
        cmds.parent(b_el, b_sh)
        cmds.parent(b_wr, b_el)

        # Resetear orientaciones para asegurar un cálculo limpio
        for jnt in [b_cl, b_sh, b_el, b_wr]:
            cmds.setAttr(f"{jnt}.jointOrient", 0, 0, 0)

        # ORIENTACIÓN DE JOINTS DEPENDIENDO DEL LADO
        if side == "R":
            # Intentamos mapear la orientación de las guías si ya vienen orientadas (ej: por mirrorJoint)
            guide_map = {
                b_cl: self.clavicule_guide,
                b_sh: self.shoulder_guide,
                b_el: self.elbow_guide,
                b_wr: self.wrist_guide,
            }
            try:
                for jnt, guide in guide_map.items():
                    jo = cmds.getAttr(f"{guide}.jointOrient")[0]
                    cmds.setAttr(f"{jnt}.jointOrient", jo[0], jo[1], jo[2])
            except:
                # Si las guías de la derecha no tienen orientación precalculada,
                # forzamos orientación simétrica clásica (sao inverso a la izquierda)
                cmds.joint(b_cl, edit=True, oj="xyz", sao="ydown", ch=True, zso=True)
                cmds.setAttr(f"{b_wr}.jointOrient", 0, 0, 0)
        else:
            # Lado L: orientación estándar automática apuntando a X
            cmds.joint(b_cl, edit=True, oj="xyz", sao="yup", ch=True, zso=True)
            cmds.setAttr(f"{b_wr}.jointOrient", 0, 0, 0)
        
        self.bind_chain = [b_sh, b_el, b_wr]
        self.b_cl = b_cl  

        # FUNCIÓN DE DUPLICADO SEGURO DE CADENAS (Asegura la posición e ignorancia de jerarquías externas)
        def duplicate_chain(suffix):
            # Duplicamos temporalmente desparentado para evitar herencias locas de la clavícula
            old_parent = cmds.listRelatives(self.bind_chain[0], parent=True)
            cmds.parent(self.bind_chain[0], world=True)
            
            new_jnts = cmds.duplicate(self.bind_chain[0], rc=True)
            
            # Restauramos el parent original de la bind chain
            if old_parent:
                cmds.parent(self.bind_chain[0], old_parent[0])
                
            root = cmds.rename(new_jnts[0], f"{self.rig_name}_{self.names[1]}_{suffix}_JNT")
            children = cmds.listRelatives(root, ad=True, type="joint")
            children.reverse()
            el = cmds.rename(children[0], f"{self.rig_name}_{self.names[2]}_{suffix}_JNT")
            wr = cmds.rename(children[1], f"{self.rig_name}_{self.names[3]}_{suffix}_JNT")
            
            # Limpiamos transformaciones de escala/posición residuales para que clonen el world matrix exacto
            for j in [root, el, wr]:
                cmds.setAttr(f"{j}.t", 0, 0, 0) if j != root else None
                
            cmds.setAttr(f"{wr}.jointOrient", 0, 0, 0)
            return [root, el, wr]
            
        self.fk_chain = duplicate_chain("fk")
        self.ik_chain = duplicate_chain("ik")

        # 3. GRUPOS DE RIG
        self.main_rig_grp = cmds.group(em=True, n=f"{self.rig_name}_armContols_GRP")
        self.main_grp = self.main_rig_grp
        self.ik_grp = cmds.group(em=True, n=f"{self.rig_name}_ik_GRP", p=self.main_rig_grp)
        self.fk_grp = cmds.group(em=True, n=f"{self.rig_name}_fk_GRP", p=self.main_rig_grp)
        self.controls_grp = cmds.group(em=True, n=f"{self.rig_name}_CONTROLS_GRP", p=self.main_rig_grp)
        self.arm_grp = cmds.group(em=True, n=f"{self.rig_name}_arm_GRP")
        
        # 4. IK SETUP Y PREFERRED ANGLE
        # El codo derecho se flexiona de manera invertida al izquierdo para mantener simetría mecánica
        flex_direction = 0.1 if side == "L" else -0.1
        cmds.setAttr(f"{self.ik_chain[1]}.rotateY", flex_direction) 
        cmds.joint(self.ik_chain[0], edit=True, ch=True, spa=True) 
        cmds.setAttr(f"{self.ik_chain[1]}.rotateY", 0) 

        # Crear ikHandle
        ik_h, ik_eff = cmds.ikHandle(sj=self.ik_chain[0], ee=self.ik_chain[2], sol="ikRPsolver", n=f"{self.rig_name}_IKH")
        cmds.select(clear=True)
        
        # CONTROL CLAVICULE
        clavicule_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["clavicule"], 
            final_name=f"{self.rig_name}_clavicule_CTRL"
        )
        clav_gen = self.group_maker.create_rig_hierarchy(clavicule_ctrl, b_cl)
        cmds.matchTransform(clav_gen, b_cl, pos=True, rot=True) # <-- Crucial: Matchear al joint bind creado
        cmds.parentConstraint(clavicule_ctrl, b_cl, mo=True)
        cmds.parent(clav_gen, self.controls_grp)
        
        # IK Root Control
        ik_root_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["root"], 
            final_name=f"{self.rig_name}_armRoot_CTRL"
        )
        ik_root_gen = self.group_maker.create_rig_hierarchy(ik_root_ctrl, self.ik_chain[0])
        cmds.matchTransform(ik_root_gen, self.ik_chain[0], pos=True, rot=True) # <-- CORRECCIÓN: Llevar el grupo al hombro IK
        cmds.pointConstraint(ik_root_ctrl, self.ik_chain[0], mo=True)
        
        # IK Handle Control (Muñeca)
        ik_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["mainIk"], 
            final_name=f"{self.rig_name}_armIk_CTRL"
        )
        ik_ctrl_gen = self.group_maker.create_rig_hierarchy(ik_ctrl, self.ik_chain[2])
        cmds.matchTransform(ik_ctrl_gen, self.ik_chain[2], pos=True, rot=False) # <-- CORRECCIÓN: Llevar el grupo a la muñeca IK
        cmds.orientConstraint(ik_ctrl, self.ik_chain[2], mo=True)        
        
        # Pole Vector (Codo)
        pv_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["poleVector"], 
            final_name=f"{self.rig_name}_poleVector_CTRL"
        )
        pv_gen = self.group_maker.create_rig_hierarchy(pv_ctrl, self.ik_chain[1], world_space=False)
        pv_pos = self.define_poleVector(self.ik_chain[0], self.ik_chain[1], self.ik_chain[2])
        cmds.xform(pv_gen, ws=True, t=pv_pos)
        cmds.poleVectorConstraint(pv_ctrl, ik_h)
        
        # Organizar elementos IK
        cmds.parent(ik_root_gen, ik_ctrl_gen, pv_gen, self.ik_grp)
        cmds.parentConstraint(ik_ctrl, ik_h, mo=True)
        cmds.parentConstraint(clavicule_ctrl, ik_root_gen, mo=True)        
        cmds.parent(ik_h, self.arm_grp)
        
        # 5. FK SETUP
        fk_ctrls = [] 
        for i in range(3):
            jnt = self.fk_chain[i]
            ctrl_name = f"{self.rig_name}_{self.names[i+1]}_fk_CTRL" 
            
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["mainFk"], 
                final_name=ctrl_name
            )
            
            gen = self.group_maker.create_rig_hierarchy(ctrl, jnt)
            cmds.matchTransform(gen, jnt, pos=True, rot=True) # <-- CORRECCIÓN: Alinear perfectamente el offset FK con su Joint
            cmds.parentConstraint(ctrl, jnt)
            fk_ctrls.append(ctrl) 
            
            if i == 0:
                cmds.parent(gen, self.fk_grp)
            else:
                cmds.parent(gen, fk_ctrls[i-1])
                
        cmds.parentConstraint(clavicule_ctl, self.fk_grp, mo=True)  
        
        # 6. SWITCH & VISIBILIDAD
        switch_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.styles["switch"], 
            final_name=f"{self.rig_name}_switch_CTRL"
        )
        switch_gen = self.group_maker.create_rig_hierarchy(switch_ctrl, self.bind_chain[2])
        cmds.matchTransform(switch_gen, self.bind_chain[2], pos=True, rot=False) # <-- CORRECCIÓN: Evita el offset hardcodeado de (0,10,0) flotante descontrolado
        cmds.xform(switch_gen, r=True, os=True, t=(0, 5, 0) if side == "L" else (0, -5, 0))
        cmds.addAttr(switch_ctrl, ln="IK_FK", at="double", min=0, max=1, k=True)
        cmds.parent(switch_gen, self.main_rig_grp)

        vis_rev = cmds.createNode("reverse", n=f"{self.rig_name}_VIS_REV")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{vis_rev}.inputX")
        cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{self.fk_grp}.visibility")
        cmds.connectAttr(f"{vis_rev}.outputX", f"{self.ik_grp}.visibility")
        
        # 7. BLEND (Pair Blends)
        for i in range(len(self.bind_chain)):
            bnd_jnt = self.bind_chain[i]
            ik_jnt = self.ik_chain[i]
            fk_jnt = self.fk_chain[i]

            pbl_creator = NodeCreator(
                side=side,   
                node_type="pairBlend",
                base_name=self.rig_name,              
                name=self.names[i+1],                   
                tag="blend",
                parent=None,
                custom_suffix=None                    
            )
            pbl = pbl_creator.create()
            
            cmds.setAttr(f"{pbl}.rotInterpolation", 1) 
            cmds.connectAttr(f"{ik_jnt}.translate", f"{pbl}.inTranslate1")
            cmds.connectAttr(f"{ik_jnt}.rotate", f"{pbl}.inRotate1")
            cmds.connectAttr(f"{fk_jnt}.translate", f"{pbl}.inTranslate2")
            cmds.connectAttr(f"{fk_jnt}.rotate", f"{pbl}.inRotate2")
            cmds.connectAttr(f"{pbl}.outTranslate", f"{bnd_jnt}.translate")
            cmds.connectAttr(f"{pbl}.outRotate", f"{bnd_jnt}.rotate")
            cmds.connectAttr(f"{switch_ctrl}.IK_FK", f"{pbl}.weight")
            
        # 8. ORGANIZACIÓN FINAL EN GRUPOS DEL PERSONAJE
        skeleton_grp = f"{self.root_instance.rig_name}_C_skeleton_GRP" if self.root_instance else None
        if skeleton_grp and cmds.objExists(skeleton_grp):
            cmds.parent(self.b_cl, skeleton_grp)

        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            # Corregido: antes tenías b_cl duplicado aquí abajo bajo el rig_grp, debe ir en el skeleton_grp
            if cmds.objExists(self.arm_grp):
                cmds.parent(self.arm_grp, rig_grp)
        
        local_ctl = self.root_instance.localCtl if self.root_instance else None
        if local_ctl and cmds.objExists(local_ctl):
            cmds.parent(self.main_grp, local_ctl)
        
        print(f"Build {self.rig_name} completo respetando guías.")

