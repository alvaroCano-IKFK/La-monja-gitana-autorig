import maya.cmds as cmds
import controls_module
import rigRoot_module
from groups_module import ControlsGroups # Importación necesaria

class SpineModule(object):

    def __init__(self,
                 root_guide="root",
                 chest_guide="chest",
                 rig_name="Character",
                 root_instance = None):

        self.root_guide = root_guide
        self.chest_guide = chest_guide
        self.rig_name = rig_name
        # Instanciamos tu clase de controles
        self.ctrl_maker = controls_module.Controls(scale=2, color=6)
        # Instanciamos el módulo de grupos
        self.group_maker = ControlsGroups()
        
        self.spine_grp = None
        self.ctrl_grp = None
        self.joints = []
        self.controls = []
        self.clusters = []
        self.root_instance = root_instance
        
    def build(self):
        if not cmds.objExists(self.root_guide):
            cmds.error("Root guide not found")

        if not cmds.objExists(self.chest_guide):
            cmds.error("Chest guide not found")

        # Crear grupos principales
        self.spine_grp = cmds.group(em=True, n=f"{self.rig_name}_spine_GRP")
        self.ctrl_grp = cmds.group(em=True, n=f"{self.rig_name}_spineControls_GRP")

        # Obtener posiciones desde guides
        pos_root = cmds.xform(self.root_guide, q=True, ws=True, t=True)
        pos_chest = cmds.xform(self.chest_guide, q=True, ws=True, t=True)

        direction = [
            pos_chest[0] - pos_root[0],
            pos_chest[1] - pos_root[1],
            pos_chest[2] - pos_root[2]
        ]

        num_cvs = 5
        cvs = []

        for i in range(num_cvs):
            t = float(i) / (num_cvs - 1)
            cvs.append([
                pos_root[0] + direction[0] * t,
                pos_root[1] + direction[1] * t,
                pos_root[2] + direction[2] * t
            ])

        # Crear curva
        spine_curve = cmds.curve(d=3, p=cvs, n=f"{self.rig_name}_spine_CRV")
        cmds.parent(spine_curve, self.spine_grp)

        previous_joint = None

        # Crear sistema
        ctrl_data = {}

        for i, cv in enumerate(cvs):
            # 1. Crear Joint y Cluster
            cmds.select(clear=True)
            jnt = cmds.joint(p=cv, n=f"{self.rig_name}_spine_{i}_JNT")
            self.joints.append(jnt)
            if i > 0: cmds.parent(jnt, self.joints[i-1])

            cluster_handle = cmds.cluster(f"{spine_curve}.cv[{i}]", n=f"{self.rig_name}_cluster_{i}")[1]
            cmds.parent(cluster_handle, self.spine_grp)

            # 2. Crear primero el Control (Para que la variable 'ctrl' exista)
            name = f"{self.rig_name}_spine_{i}_CTL"
            ctrl = self.ctrl_maker.circle_ctl_builder(name=name, radius=2)
            
            # 3. Crear la jerarquía de grupos (Pasándole el control ya creado)
            # El método create_rig_hierarchy devuelve el nombre del grupo raíz (GRP)
            spine_grp_root = self.group_maker.create_rig_hierarchy(ctrl, cluster_handle) 
            
            # 4. Guardamos los nodos (Usamos spine_grp_root como el 'top')
            ctrl_data[i] = {'ctrl': ctrl, 'top': spine_grp_root, 'cluster': cluster_handle}
            self.controls.append(ctrl)

        # 2. SECCIÓN DE JERARQUÍA
        # spine_0 es el top, va al grupo de controles
        cmds.parent(ctrl_data[0]['top'], self.ctrl_grp)
        
        # spine_2 y spine_1 van dentro de spine_0
        cmds.parent(ctrl_data[2]['top'], ctrl_data[0]['ctrl'])
        cmds.parent(ctrl_data[1]['top'], ctrl_data[0]['ctrl'])
        
        # spine_4 va dentro de spine_2
        cmds.parent(ctrl_data[4]['top'], ctrl_data[2]['ctrl'])
        
        # spine_3 va dentro de spine_4
        cmds.parent(ctrl_data[3]['top'], ctrl_data[4]['ctrl'])

        # 3. CONEXIONES FINALES
        for i in ctrl_data:
            cmds.parentConstraint(ctrl_data[i]['ctrl'], ctrl_data[i]['cluster'], mo=True)

        # 5. IK spline
        ik, eff = cmds.ikHandle(
            sj=self.joints[0],
            ee=self.joints[-1],
            sol="ikSplineSolver",
            c=spine_curve,
            ccv=False,
            pcv=False,
            n=f"{self.rig_name}_spine_IK"
        )

        cmds.parent(ik, self.spine_grp)
        cmds.parent(self.joints[0], self.spine_grp)
        
        # --- SECCIÓN DE ORGANIZACIÓN FINAL ---
        
        rig_name = self.root_instance.rig_name if self.root_instance else "Character"
        local_ctl = self.root_instance.localCtl if self.root_instance else None
        
        # 1. Emparentar la estructura de joints/IK al grupo de rig (Sistemas/No tocables)
        rig_system_grp = f"{rig_name}_rig_GRP"
        if cmds.objExists(rig_system_grp):
            cmds.parent(self.spine_grp, rig_system_grp)
        
        # 2. Emparentar los controles de la espina al LOCAL CONTROL
        # En lugar de emparentar 'top', emparentamos el contenedor de la espina
        if local_ctl and cmds.objExists(local_ctl):
            cmds.parent(self.ctrl_grp, local_ctl)
            print(f"DEBUG: Espina emparentada a control local: {local_ctl}")
        else:
            # Si no hay local_ctl, lo mandamos al grupo de controles global como backup
            global_controls_grp = f"{rig_name}_controls_GRP"
            if cmds.objExists(global_controls_grp):
                cmds.parent(self.ctrl_grp, global_controls_grp)
                
        print("DEBUG: local_ctl no encontrado, emparentado a global_controls_GRP")
        print(f"Spine para {self.rig_name} creada con éxito.")
        return self
        