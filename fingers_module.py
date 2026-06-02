import maya.cmds as cmds
import controlsLibrary
import groups_module  

class FingersModule(object):

    def __init__(self, wrist_guide="wrist", rig_name="Character", side="L", root_instance=None):
        self.wrist_guide    = wrist_guide
        self.rig_name       = rig_name
        self.side           = side
        self.styles         = {"finger": "fingerControl"}
        self.group_maker    = groups_module.ControlsGroups()

        self.joints_master_grp = None
        self.ctrls_master_grp  = None
        self.root_instance     = root_instance

        self.prefix = f"{self.side}_{self.rig_name}"
        self.names  = ["clavicule", "shoulder", "elbow", "wrist"]


    def get_finger_roots(self):
        """Obtiene las guías raíz de los dedos como hijos del wrist_guide."""
        return cmds.listRelatives(self.wrist_guide, c=True, type="joint") or []


    def build_finger_from_guides(self, guide_root):
        """Construye una cadena de joints calcando la jerarquía y rotación exacta de las guías."""
        # 1. Encontrar la cadena de guías respetando estrictamente el orden jerárquico descendente
        guide_chain = [guide_root]
        current = guide_root
        while True:
            children = cmds.listRelatives(current, c=True, type="joint")
            if not children:
                break
            guide_chain.append(children[0])
            current = children[0]

        rig_chain = []
        cmds.select(clear=True)

        # 2. Crear los joints copiando posición Y rotación (orientación) de cada guía
        parent_jnt = None
        for guide in guide_chain:
            jnt_name = f"{self.prefix}_{guide}_JNT"
            
            # Creamos el joint
            new_joint = cmds.joint(n=jnt_name)
            
            # Lo emparejamos con su padre de la cadena actual si existe
            #if parent_jnt:
                #cmds.parent(new_joint, parent_jnt)
                
            # Copiamos la posición y orientación exacta de la guía mediante un parentConstraint temporal
            temp_constraint = cmds.parentConstraint(guide, new_joint, mo=False)
            cmds.delete(temp_constraint)
            
            # Congelamos las transformaciones para que los valores de rotación vayan a las orientaciones del joint (Joint Orient)
            cmds.makeIdentity(new_joint, apply=True, t=0, r=1, s=0, n=0, pn=1)
            
            rig_chain.append(new_joint)
            parent_jnt = new_joint

        return rig_chain


    def build(self):
        """Construye los dedos de la mano para el lado definido en self.side."""
        self.ctrls_master_grp = cmds.group(em=True, n=f"{self.prefix}_Fingers_CTRL_GRP")

        target_bind_wrist = f"{self.prefix}_{self.names[3]}_bind_JNT"
        finger_roots      = self.get_finger_roots()

        for root in finger_roots:
            # 1. Crear joints del dedo (ahora calcan perfectamente la guía)
            rig_chain = self.build_finger_from_guides(root)

            # 2. Emparentar primer joint del dedo bajo el bind wrist
            if cmds.objExists(target_bind_wrist):
                cmds.parent(rig_chain[0], target_bind_wrist)

            # 3. Crear controles y constreñir al wrist
            self.create_finger_controls(rig_chain, target_bind_wrist)

        # ---- ORGANIZACIÓN FINAL ----
        if self.side == "R":
            # Lado R: va bajo mirrorBehaviour_GRP (el cual se encarga de invertir el comportamiento gracias al scaleX -1)
            mirror_grp = f"{self.root_instance.rig_name}_mirrorBehaviour_GRP" if self.root_instance else f"Character_mirrorBehaviour_GRP"
            if cmds.objExists(mirror_grp):
                cmds.parent(self.ctrls_master_grp, mirror_grp)
            else:
                cmds.warning(f"fingers build: no existe {mirror_grp}")
        else:
            # Lado L: va bajo localCtl
            local_ctl = self.root_instance.localCtl if self.root_instance else None
            if local_ctl and cmds.objExists(local_ctl):
                cmds.parent(self.ctrls_master_grp, local_ctl)

        print(f"Build {self.prefix} completo.")
        
        
    def create_finger_controls(self, rig_chain, bind_wrist):
        """Crea controles para cada joint del dedo y los constriñe al wrist."""
        controls = []
        for i, jnt in enumerate(rig_chain[:-1]):
            ctrl_name = jnt.replace("_JNT", "_CTRL")
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.styles["finger"],
                final_name=ctrl_name
            )

            # Modificamos la jerarquía del grupo (suponiendo que tu group_maker orienta el grupo igual que el joint)
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