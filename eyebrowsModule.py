import math
import maya.cmds as cmds
import maya.api.OpenMaya as om2

import controlsLibrary
import groups_module
import guides_module
import rigRoot_module
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator


class EyebrowsModule(object):

    def __init__(
        self,
        guide_prefix="L_eyebrow_root",
        num_joints=10,
        rig_name="Character",
        side="L",
        root_instance=None,
        **kwargs,
    ):
        self.guide_prefix = guide_prefix
        self.num_joints = num_joints
        self.side = side
        self.rig_name = rig_name
        self.prefix = f"{self.side}_{rig_name}_eyebrow"

        self.group_maker = groups_module.ControlsGroups()
        self.root_instance = root_instance
        self.control_style = "circleControl"

        self.main_control_style = kwargs.get(
            "main_control_style", self.control_style
        )
        self.corner_control_style = kwargs.get(
            "corner_control_style", self.control_style
        )
        self.tangent_control_style = kwargs.get(
            "tangent_control_style", self.control_style
        )

        # Paràmetres configurables de la bezier / upCurve
        self.mid_tangent_scale = kwargs.get("mid_tangent_scale", 0.15)
        self.up_curve_offset = kwargs.get("up_curve_offset", 0.5)

        # NORMAL DEL PLA de l'offset, NO la direcció del desplaçament.
        # La direcció real de l'offset és tangent x normal.
        #   (0, -1, 0) -> desplaçament horitzontal, paral·lel al terra.
        #                 És el que descriu la infografia: la upCurve queda
        #                 davant de la cara i els joints hi aimen.
        #   (0,  0, 1) -> desplaçament vertical, la upCurve queda per sobre
        #                 de l'arc de la cella.
        self.up_curve_normal = kwargs.get("up_curve_normal", (0.0, -1.0, 0.0))

        # Cap on ha d'apuntar l'offset en world space. Com que la direcció
        # depèn del sentit In->Out de la corba, sense això la upCurve de L i
        # la de R acaben a bandes oposades del crani. Amb la cara mirant a
        # +Z, deixa-ho a (0, 0, 1).
        self.up_curve_aim = kwargs.get("up_curve_aim", (0.0, 0.0, 1.0))

        self.rig_joints = []
        self.controls = []
        self.control_groups = []

        self.module_grp = None
        self.joints_grp = None
        self.controls_grp = None
        self.local_grp = None

        self.local_joints = {}
        self.local_transforms = {}
        self.local_curve = None
        self.local_up_curve = None

    # ------------------------------------------------------------------
    # Connectors i creadors de transformacions relatives / locals
    # ------------------------------------------------------------------
    def generate_relative_control_transform(
        self, control_name, top_grp, create_transform=True
    ):

        base_name = control_name.replace("_CTRL", "").replace("_ctl", "")
        grp = cmds.listRelatives(control_name, parent=True, type="transform")[0]

        # Creació del nodo multMatrix
        mmtx = cmds.createNode(
            "multMatrix", name=f"{base_name}Local_MTX", ss=True
        )

        # Cerca de la jerarquia fins a top_grp
        hierarchy_transforms = []
        current_node = [control_name]

        while current_node:
            node_name = current_node[0]
            hierarchy_transforms.append(node_name)
            if node_name == top_grp:
                break
            current_node = cmds.listRelatives(
                node_name, parent=True, type="transform"
            )

        matrix_inputs = list(reversed(hierarchy_transforms))

        for i, elem in enumerate(matrix_inputs):
            cmds.connectAttr(
                f"{elem}.matrix", f"{mmtx}.matrixIn[{i}]", force=True
            )

        # Neutralitzem l'offset estàtic (bind pose) perquè el resultat
        # sigui 0/identitat en repòs, independentment de la posició de la guia.
        bind_matrix = cmds.getAttr(f"{mmtx}.matrixSum")
        inv_bind_matrix = om2.MMatrix(bind_matrix).inverse()
        bind_index = len(matrix_inputs)
        cmds.setAttr(
            f"{mmtx}.matrixIn[{bind_index}]",
            list(inv_bind_matrix),
            type="matrix",
        )

        # Creació del nodo decomposeMatrix
        dcm = cmds.createNode(
            "decomposeMatrix", name=f"{base_name}Local_DCM", ss=True
        )
        cmds.connectAttr(f"{mmtx}.matrixSum", f"{dcm}.inputMatrix", force=True)

        if not create_transform:
            return dcm

        # Creació del grup REL (mantenint la posició neutra)
        relative_trn = cmds.createNode(
            "transform", name=f"{base_name}_REL", ss=True
        )
        cmds.parent(relative_trn, grp, relative=True)

        for out_attr, in_attr in (
            ("outputTranslate", "translate"),
            ("outputRotate", "rotate"),
            ("outputScale", "scale"),
        ):
            cmds.connectAttr(
                f"{dcm}.{out_attr}", f"{relative_trn}.{in_attr}", force=True
            )

        return relative_trn, dcm

    def _connect_transform_channels(self, driver_node, driven_node):
        """Connecta Translate, Rotate i Scale d'un nodo/transform a un altre."""
        for attr in ("translate", "rotate", "scale"):
            cmds.connectAttr(
                f"{driver_node}.{attr}", f"{driven_node}.{attr}", force=True
            )

    # ------------------------------------------------------------------
    # Local joint helper
    # ------------------------------------------------------------------
    def _create_local_joint(self, parent_trn, name):
        cmds.select(clear=True)
        jnt = cmds.joint(name=name)
        cmds.parent(jnt, parent_trn, relative=True)
        return jnt

    # ------------------------------------------------------------------
    # Curve helpers
    # ------------------------------------------------------------------
    def _cv_count(self, curve):
        """Nombre real de CVs d'una corba (funciona també per a beziers)."""
        return len(cmds.ls(f"{curve}.cv[*]", flatten=True))

    def _park_curve_in_local_grp(self, curve):
        """Parenteja una corba al grup local sense heretar transformacions.

        Les dues corbes han de viure al mateix espai. Com que després es
        deformen amb un skinCluster, cal desactivar l'inheritsTransform per
        evitar la doble transformació del grup local.
        """
        if not (self.local_grp and cmds.objExists(self.local_grp)):
            return

        cmds.parent(curve, self.local_grp, relative=True)
        cmds.setAttr(f"{curve}.inheritsTransform", 0)

    def _skin_curve_one_to_one(self, curve, cv_weights, skin_name):
        """Skinneja una corba amb una única influència per CV.

        cv_weights: dict {cv_index: joint}
        """
        cv_count = self._cv_count(curve)
        if cv_count != len(cv_weights):
            cmds.warning(
                f"{curve} té {cv_count} CVs i se n'esperaven "
                f"{len(cv_weights)}. No es pot fer el skin 1:1; revisa el "
                "subdivisionDensity o la distància de l'offsetCurve."
            )
            return None

        joints = list(dict.fromkeys(cv_weights.values()))
        skin_cluster = cmds.skinCluster(joints, curve, tsb=True, n=skin_name)[0]

        for cv_index, jnt in cv_weights.items():
            cmds.skinPercent(
                skin_cluster,
                f"{curve}.cv[{cv_index}]",
                transformValue=[(jnt, 1.0)],
            )
        return skin_cluster

    def _measure_offset_direction(self, source_curve, offset_curve):
        """Vector que va del punt mig de la corba font al de l'offset."""
        src = cmds.pointOnCurve(source_curve, pr=0.5, top=True, p=True)
        off = cmds.pointOnCurve(offset_curve, pr=0.5, top=True, p=True)
        return om2.MVector(
            off[0] - src[0], off[1] - src[1], off[2] - src[2]
        )

    # ------------------------------------------------------------------
    # Bezier curve creation
    # ------------------------------------------------------------------
    def _create_local_bezier_curve(self):
        required_labels = ("In", "InTan", "Mid", "OutTan", "Out")
        if not all(label in self.local_joints for label in required_labels):
            cmds.warning(
                "No es poden trobar tots els joints locals necessaris per crear la bezierCurve."
            )
            return None

        in_jnt = self.local_joints["In"]
        in_tan_jnt = self.local_joints["InTan"]
        mid_jnt = self.local_joints["Mid"]
        out_tan_jnt = self.local_joints["OutTan"]
        out_jnt = self.local_joints["Out"]

        in_pos = cmds.xform(in_jnt, q=True, ws=True, t=True)
        in_tan_pos = cmds.xform(in_tan_jnt, q=True, ws=True, t=True)
        mid_pos = cmds.xform(mid_jnt, q=True, ws=True, t=True)
        out_tan_pos = cmds.xform(out_tan_jnt, q=True, ws=True, t=True)
        out_pos = cmds.xform(out_jnt, q=True, ws=True, t=True)

        # Càlcul vectorial de les tangents del Mid (ajustable via mid_tangent_scale)
        tangent_scale = self.mid_tangent_scale
        mid_dir = [out_pos[axis] - in_pos[axis] for axis in range(3)]
        mid_in_tan_pos = [
            mid_pos[axis] - mid_dir[axis] * tangent_scale for axis in range(3)
        ]
        mid_out_tan_pos = [
            mid_pos[axis] + mid_dir[axis] * tangent_scale for axis in range(3)
        ]

        # 3 àncores (In, Mid, Out). In i Out són "corner" per definició
        # (un sol handle a cada extrem); Mid té tangents suaus i col·lineals.
        cv_positions = [
            in_pos,
            in_tan_pos,
            mid_in_tan_pos,
            mid_pos,
            mid_out_tan_pos,
            out_tan_pos,
            out_pos,
        ]

        bezier_crv = cmds.curve(
            bezier=True,
            d=3,
            p=cv_positions,
            k=[0, 0, 0, 1, 1, 1, 2, 2, 2],
            n=f"{self.prefix}_local_BZC",
        )

        cv_weights = {
            0: in_jnt,
            1: in_tan_jnt,
            2: mid_jnt,
            3: mid_jnt,
            4: mid_jnt,
            5: out_tan_jnt,
            6: out_jnt,
        }

        # La upCurve es genera ABANS d'skinnejar, a partir de la forma neta.
        up_curve = self._create_local_up_curve(bezier_crv)

        # Les dues corbes al mateix espai
        self._park_curve_in_local_grp(bezier_crv)
        if up_curve:
            self._park_curve_in_local_grp(up_curve)

        # Skin 1:1 de totes dues (pas 8 de la infografia)
        self._skin_curve_one_to_one(
            bezier_crv, cv_weights, f"{self.prefix}_local_curve_SKIN"
        )
        if up_curve:
            self._skin_curve_one_to_one(
                up_curve, cv_weights, f"{self.prefix}_local_upCurve_SKIN"
            )

        self.local_curve = bezier_crv
        return bezier_crv

    # ------------------------------------------------------------------
    # Up curve (offsetCurve directe sobre un duplicat net de la bezier)
    # ------------------------------------------------------------------
    def _create_local_up_curve(self, source_curve):

        # 1) Duplicat net. Conservem la forma bezier (mateixos CVs i mateixos
        #    anchor presets) i eliminem qualsevol historial heretat.
        tmp_crv = cmds.duplicate(
            source_curve, name=f"{self.prefix}_upCRV_src_TMP"
        )[0]
        cmds.delete(tmp_crv, ch=True)

        def _build_offset(distance, node_name):
            result = cmds.offsetCurve(
                tmp_crv,
                ch=False,          # sense history: la volem estàtica
                rn=False,
                cb=2,              # Connect Breaks: Linear
                cl=True,           # Cut Loop
                cr=0.0,            # Cut Radius 0
                d=distance,
                tol=0.01,
                sd=0,              # CLAU: conserva el nombre de CVs
                ugn=True,          # useGivenNormal
                normal=self.up_curve_normal,
                name=node_name,
            )
            return result[0] if isinstance(result, list) else result

        # 2) Primer intent amb distància positiva
        up_curve = _build_offset(
            self.up_curve_offset, f"{self.prefix}_local_upCRV"
        )

        # 3) Comprovació del signe. La direcció de l'offset és tangent x normal,
        #    i com que la corba va In->Out, a L i a R surt invertida. Si apunta
        #    al contrari de up_curve_aim, la refem negada.
        delta = self._measure_offset_direction(tmp_crv, up_curve)
        aim = om2.MVector(*self.up_curve_aim)

        if delta.length() > 1e-6 and aim.length() > 1e-6:
            if (delta.normal() * aim.normal()) < 0.0:
                cmds.delete(up_curve)
                up_curve = _build_offset(
                    -self.up_curve_offset, f"{self.prefix}_local_upCRV"
                )

        # 4) Neteja del duplicat temporal
        if cmds.objExists(tmp_crv):
            cmds.delete(tmp_crv)

        self.local_up_curve = up_curve
        return up_curve

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build(self):
        base_prefix = self.guide_prefix.replace("L_", "").replace("R_", "")

        # 1) JOINTS
        created_joints = []
        for i in range(1, self.num_joints + 1):
            guide_name = f"{self.side}_{base_prefix}_{i:02d}"

            if cmds.objExists(guide_name):
                pos = cmds.xform(guide_name, q=True, ws=True, t=True)
                rot = cmds.xform(guide_name, q=True, ws=True, ro=True)

                cmds.select(clear=True)
                jnt_name = f"{self.prefix}_{i:02d}_bind_JNT"
                jnt = cmds.joint(name=jnt_name, p=pos)
                cmds.setAttr(f"{jnt}.rotate", *rot)
                created_joints.append(jnt)
            else:
                cmds.warning(f"No s'ha trobat la guia: {guide_name}")

        self.rig_joints = created_joints

        if not created_joints:
            return

        # 2) MAIN CONTROL
        main_ctl_grp = cmds.group(em=True, n=f"{self.prefix}_main_ctrl_GRP")
        self.controls_grp = main_ctl_grp

        mid_idx = max(1, math.ceil(self.num_joints / 2.0))
        mid_guide_name = f"{self.side}_{base_prefix}_{mid_idx:02d}"

        main_ctl = controlsLibrary.create_control_from_lib(
            lib_name=self.main_control_style,
            final_name=f"{self.prefix}_Main_CTRL",
        )
        main_ctl_gen = self.group_maker.create_rig_hierarchy(
            main_ctl, mid_guide_name
        )
        cmds.parent(main_ctl_gen, main_ctl_grp)

        if not cmds.attributeQuery("slide", node=main_ctl, exists=True):
            cmds.addAttr(
                main_ctl,
                longName="slide",
                attributeType="float",
                defaultValue=1.0,
                minValue=0.0,
                maxValue=1.0,
                keyable=True,
            )

        self.controls.append(main_ctl)
        self.control_groups.append(main_ctl_gen)

        # 3) LOCAL MAIN GROUP
        main_local_off = cmds.group(em=True, n=f"{self.prefix}MainLocal_OFF")
        cmds.matchTransform(main_local_off, main_ctl_gen, pos=True, rot=True)

        main_local_trn = cmds.group(
            em=True, n=f"{self.prefix}MainLocal_TRN", p=main_local_off
        )
        self.local_grp = main_local_off
        self.local_transforms["Main"] = main_local_trn

        # 4) CONTROLS SECUNDARIS
        sub_indices = {
            "In": 1,
            "Mid": mid_idx,
            "Out": self.num_joints,
        }
        corner_labels = ("In", "Out")

        for label, idx in sub_indices.items():
            sub_guide_name = f"{self.side}_{base_prefix}_{idx:02d}"
            if not cmds.objExists(sub_guide_name):
                cmds.warning(f"No s'ha trobat la guia: {sub_guide_name}")
                continue

            sub_ctrl_name = f"{self.prefix}_{label}_CTRL"
            sub_ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.corner_control_style, final_name=sub_ctrl_name
            )
            sub_ctl_gen = self.group_maker.create_rig_hierarchy(
                sub_ctrl, sub_guide_name
            )
            cmds.parent(sub_ctl_gen, main_ctl)

            # Generació del grup REL i la xarxa de matrius
            rel_grp, _ = self.generate_relative_control_transform(
                control_name=sub_ctrl,
                top_grp=main_ctl_grp,
                create_transform=True,
            )

            self.controls.append(sub_ctrl)
            self.control_groups.append(sub_ctl_gen)

            # Estructura de grups Locals (OFF + TRN)
            local_off = cmds.group(
                em=True, n=f"{self.prefix}{label}Local_OFF", p=main_local_trn
            )
            cmds.matchTransform(local_off, sub_ctl_gen, pos=True, rot=True)

            local_trn = cmds.group(
                em=True, n=f"{self.prefix}{label}Local_TRN", p=local_off
            )
            self.local_transforms[label] = local_trn

            # Connexió des del REL cap al TRN (Mantenint TRN a 0, 0, 0)
            self._connect_transform_channels(rel_grp, local_trn)

            local_jnt = self._create_local_joint(
                local_trn, f"{self.prefix}{label}Local_JNT"
            )
            self.local_joints[label] = local_jnt

            # Controls de tangent per a les cantonades
            if label in corner_labels:
                neighbour_idx = 2 if label == "In" else self.num_joints - 1
                neighbour_guide = (
                    f"{self.side}_{base_prefix}_{neighbour_idx:02d}"
                )

                sub_pos = cmds.xform(sub_guide_name, q=True, ws=True, t=True)
                if cmds.objExists(neighbour_guide):
                    nb_pos = cmds.xform(
                        neighbour_guide, q=True, ws=True, t=True
                    )
                else:
                    nb_pos = sub_pos

                tangent_factor = 0.3
                tangent_pos = [
                    sub_pos[0] + (nb_pos[0] - sub_pos[0]) * tangent_factor,
                    sub_pos[1] + (nb_pos[1] - sub_pos[1]) * tangent_factor,
                    sub_pos[2] + (nb_pos[2] - sub_pos[2]) * tangent_factor,
                ]

                tangent_ctl_name = f"{self.prefix}_{label}Tan_CTRL"
                tangent_ctl = controlsLibrary.create_control_from_lib(
                    lib_name=self.tangent_control_style,
                    final_name=tangent_ctl_name,
                )

                tangent_ctl_gen = self.group_maker.create_rig_hierarchy(
                    tangent_ctl, sub_guide_name
                )
                cmds.xform(tangent_ctl_gen, ws=True, t=tangent_pos)
                cmds.parent(tangent_ctl_gen, sub_ctrl)

                # Creador de matriu i grup REL per a la tangent
                tan_rel_grp, _ = self.generate_relative_control_transform(
                    control_name=tangent_ctl,
                    top_grp=sub_ctl_gen,
                    create_transform=True,
                )

                self.controls.append(tangent_ctl)
                self.control_groups.append(tangent_ctl_gen)

                tan_label = f"{label}Tan"
                tan_local_off = cmds.group(
                    em=True,
                    n=f"{self.prefix}{tan_label}Local_OFF",
                    p=local_trn,
                )
                cmds.matchTransform(
                    tan_local_off, tangent_ctl_gen, pos=True, rot=True
                )

                tan_local_trn = cmds.group(
                    em=True, n=f"{self.prefix}{tan_label}Local_TRN", p=tan_local_off
                )
                self.local_transforms[tan_label] = tan_local_trn

                # Connexió del REL de la tangent al seu respectiu TRN
                self._connect_transform_channels(tan_rel_grp, tan_local_trn)

                tan_local_jnt = self._create_local_joint(
                    tan_local_trn, f"{self.prefix}{tan_label}Local_JNT"
                )
                self.local_joints[tan_label] = tan_local_jnt

        # 5) BEZIER CURVE + UP CURVE
        self._create_local_bezier_curve()
