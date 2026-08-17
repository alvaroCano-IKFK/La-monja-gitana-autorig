import groups_module
import maya.cmds as cmds
import guides_module
import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator
import rigRoot_module


class EyebrowsModule(object):

    def __init__(self, guide_prefix="L_eyebrow_root", num_joints=10, rig_name="Character", side="L", root_instance=None, **kwargs):
        self.guide_prefix = guide_prefix
        self.num_joints = num_joints
        self.side = side
        self.rig_name = rig_name
        self.prefix = f"{self.side}_{rig_name}_eyebrow"

        self.group_maker = groups_module.ControlsGroups()
        self.root_instance = root_instance
        self.control_style = "circleControl"

        self.rig_joints = []
        self.controls = []
        self.control_groups = []
        self.side_grp = None

    def _get_or_create_side_grp(self):
        """
        Grup general unic per side (L_GRP / R_GRP). Si ja existeix
        (per exemple perque un altre modul del mateix side ja l'ha creat),
        el reutilitzem en lloc de duplicar-lo.
        """
        side_grp_name = f"{self.side}_GRP"
        if cmds.objExists(side_grp_name):
            return side_grp_name

        cmds.select(clear=True)
        return cmds.group(em=True, n=side_grp_name, world=True)

    def build(self):
        self.side_grp = self._get_or_create_side_grp()

        for i in range(1, self.num_joints + 1):
            base_prefix = self.guide_prefix.replace("L_", "").replace("R_", "")
            guide_name = f"{self.side}_{base_prefix}_{i:02d}"

            if not cmds.objExists(guide_name):
                cmds.warning(f" No s'ha trobat la guia: {guide_name}")
                continue

            pos = cmds.xform(guide_name, q=True, ws=True, t=True)
            rot = cmds.xform(guide_name, q=True, ws=True, ro=True)

            # ---------- JOINT ----------
            cmds.select(clear=True)
            jnt_name = f"{self.prefix}_{i:02d}_bind_JNT"
            jnt = cmds.joint(name=jnt_name, p=pos)
            cmds.setAttr(f"{jnt}.rotate", *rot)

            # Parentat explicit i incondicional, sense dependre de si
            # "ja esta a world" o no. Aixi no hi ha ambiguitat mai,
            # independentment de quin sigui el primer joint o no.
            cmds.parent(jnt, self.side_grp)
            self.rig_joints.append(jnt)

            # ---------- CONTROL ----------
            cmds.select(clear=True)
            ctrl_name = f"{self.prefix}_{i:02d}_CTRL"
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.control_style,
                final_name=ctrl_name
            )

            # Sense create_rig_hierarchy per ara: nomes movem el control
            # a la posicio/rotacio de la guia, sense generar cap grup offset.
            cmds.xform(ctrl, ws=True, t=pos)
            cmds.xform(ctrl, ws=True, ro=rot)

            cmds.parent(ctrl, self.side_grp)

            cmds.parentConstraint(ctrl, jnt, mo=True)

            self.controls.append(ctrl)

        cmds.select(clear=True)
        print(f"Build {self.prefix} complet amb èxit.")