import maya.cmds as cmds
import controlsLibrary
from groups_module import ControlsGroups


class HorseTail(object):
    """
    Cua del caball: cadena FK.

    Guies (guides_module.HorseTailGuides): tail_01 -> tail_02 -> ... -> tail_05

    Build:
      - Un joint per guia, en cadena.
      - Un control per joint, en jerarquia (cada control penja de l anterior),
        amb parentConstraint al seu joint.
      - L arrel de la cua segueix la pelvis de l espina (parent_joint).
    """

    def __init__(self,
                 guides=None,
                 rig_name="Character",
                 parent_joint=None,
                 root_instance=None):
        # Per defecte, les 5 guies de guides_module.HorseTailGuides
        self.guides = guides or [f"tail_{i + 1:02d}" for i in range(5)]
        self.rig_name = rig_name
        self.parent_joint = parent_joint
        self.root_instance = root_instance

        self.ctrl_style = "circleControl"
        self.group_maker = ControlsGroups()

        self.joints = []
        self.controls = []
        self.ctrl_grp = None
        self.jnt_grp = None

    # ------------------------------------------------------------------ #
    def build(self):
        missing = [g for g in self.guides if not cmds.objExists(g)]
        if missing:
            cmds.error(f"[HorseTail] Falten guies: {missing}")

        n = self.rig_name

        # --- Joints ---------------------------------------------------------
        cmds.select(clear=True)
        self.joints = []
        for i, guide in enumerate(self.guides):
            pos = cmds.xform(guide, q=True, ws=True, t=True)
            jnt = cmds.joint(p=pos, n=f"{n}_tail_{i + 1:02d}_JNT")   #penja de l anterior
            self.joints.append(jnt)
        cmds.select(clear=True)

        # X al llarg de la cua, Y cap amunt
        cmds.joint(self.joints[0], e=True, oj="xyz", sao="yup", ch=True, zso=True)
        cmds.setAttr(f"{self.joints[-1]}.jointOrient", 0, 0, 0)

        # --- Controls en jerarquia -------------------------------------------
        self.ctrl_grp = cmds.createNode("transform", n=f"{n}_tailControls_GRP")
        self.controls = []
        tops = []
        for i, jnt in enumerate(self.joints):
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.ctrl_style,
                final_name=f"{n}_tail_{i + 1:02d}_CTRL"
            )
            top = self.group_maker.create_rig_hierarchy(ctrl, jnt)   #orientat al joint
            if i == 0:
                cmds.parent(top, self.ctrl_grp)
            else:
                cmds.parent(top, self.controls[i - 1])
            self.controls.append(ctrl)
            tops.append(top)

        for ctrl, jnt in zip(self.controls, self.joints):
            cmds.parentConstraint(ctrl, jnt, mo=True, n=f"{jnt}_PAC")

        # --- Organitzacio -----------------------------------------------------
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(self.joints[0], rig_grp)

        container = None
        if self.root_instance:
            container = (getattr(self.root_instance, "localCtl", None)
                         or getattr(self.root_instance, "body_ctl", None))
        if container and cmds.objExists(container):
            self.ctrl_grp = cmds.parent(self.ctrl_grp, container)[0]

        # L arrel de la cua segueix la pelvis de l espina
        if self.parent_joint and cmds.objExists(self.parent_joint):
            cmds.parentConstraint(self.parent_joint, tops[0], mo=True,
                                  n=f"{n}_tailBase_follow_PAC")
        else:
            cmds.warning(f"[HorseTail] No s ha trobat {self.parent_joint}: "
                         f"la cua no segueix l espina.")

        print(f"[HorseTail] Cua construida: {len(self.joints)} joints FK.")
        return self