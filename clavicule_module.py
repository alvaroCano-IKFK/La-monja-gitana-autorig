import maya.cmds as cmds
import controls_module

# now canvi

class ClaviculeModule(object):
    def __init__(self, clavicule_root="clavicule", rig_name="Character"):
        self.clavicule_guides = clavicule_root        
        self.rig_name = rig_name
        self.ctrl_maker = controls_module.Controls(scale=1, color=17)
                
    def build(self):
        # 1. Verificar existencia de la guía
        if not cmds.objExists(self.clavicule_guides):
            cmds.warning(f"La guía {self.clavicule_guides} no existe.")
            return

        # 2. Obtener posición exacta en el mundo
        clavi_pos = cmds.xform(self.clavicule_guides, q=True, ws=True, t=True)
        
        # 3. Crear el joint y posicionarlo
        cmds.select(clear=True)
        clavi_joint = cmds.joint(n=f"{self.rig_name}_clavicule_joint", p=clavi_pos)
        
        # 4. Crear el control y su offset
        name = f"{self.rig_name}_clavicule_CTL"
        claviculeControl = self.ctrl_maker.lollipop_ctl_builder(name=name)
        offset = cmds.group(claviculeControl, n=f"{claviculeControl}_offset")
        
        # Mover el offset a la posición de la guía antes de emparentar
        cmds.matchTransform(offset, self.clavicule_guides)
        
        # 5. Emparentar el offset al controlador (si es necesario) o al grupo principal
        # 6. CONECTAR: El joint de la clavícula debe seguir al control
        cmds.parentConstraint(claviculeControl, clavi_joint, mo=True)
        
        # 7. CONECTAR AL BRAZO: El joint del hombro debe ser hijo del joint de la clavícula
        shoulder_jnt_name = f"{self.rig_name}_shoulder_bind_JNT"
        if cmds.objExists(shoulder_jnt_name):
            cmds.parent(shoulder_jnt_name, clavi_joint)
            
        return clavi_joint