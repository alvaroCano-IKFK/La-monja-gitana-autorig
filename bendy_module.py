# -*- coding: utf-8 -*-
"""
bendy_module.py
===============

Bendies para extremidades de dos segmentos: brazo y pierna.

Sigue la infografia del curso (BENDIES: "mixed concepts of the twist and
curvature"), pero sin rehacer el twist: se apoya en el TwistModule que ya ha
construido la extremidad y reaprovecha sus motionPath.

Por segmento (upper y lower):

    twist MPA 0 / 2 / 4  ->  root / mid / tip DRV   (llevan posicion, curvature y twist)
    mid DRV              ->  parentConstraint  ->  bendy_CTRL (su grupo)
    bendy_CTRL           ->  parent + scaleConstraint  ->  bendy DRV
    root / bendy / tip   ->  skinCluster  ->  bendy_CRV y bendyOffset_CRV
    bendy_CRV            ->  5 motionPath  ->  5 joints de salida (_JNT, los de skin)
    bendyOffset_CRV      ->  5 motionPath  ->  5 TRN de up vector
    joints               ->  aimConstraint en cadena (el ultimo mira atras)

Con bendies, el twist NO crea sus cinco joints por segmento: los de skin pasan
a ser los de aqui (es el "instead of creating 5 output joints in the twist,
create just 3" del PDF). Eso lo controla create_joints= en
TwistModule.create_basic_curve.

Uso (lo hacen limbs_module y leg_module si la feature 'bendies' esta marcada):

    bendy = BendyModule(name="arm", side="L", twist=self.twist,
                        root_instance=self.root_instance,
                        settings_ctrl=self.switch_ctrl)
    bendy.build()
"""

import math

import maya.cmds as cmds

import controlsLibrary
from groups_module import ControlsGroups
from nodeCreator_module import NodeCreator


class BendyModule(object):

    SEGMENTS = ("upper", "lower")

    #: Que motionPath del twist hace de root, mid y tip. El twist reparte los
    #: suyos en u = 0.01, 0.255, 0.5, 0.745, 0.99, asi que el 2 cae justo en
    #: el centro del segmento y el 4 lleva el twist entero.
    DRIVER_INDICES = (("Root", 0), ("Mid", 2), ("Tip", 4))

    #: Joints de salida por segmento.
    NUM_JOINTS = 5

    #: CV del bezier -> influencia que lo mueve al 100%. Es la tabla del
    #: componentEditor del PDF: esquinas al root y al tip, anchor del medio y
    #: sus dos tangentes al bendy. Las tangentes de las esquinas (1 y 5) van
    #: con su esquina: asi el segmento sale del codo/hombro siguiendo el hueso.
    CV_WEIGHTS = {0: "Root", 1: "Root",
                  2: "Bendy", 3: "Bendy", 4: "Bendy",
                  5: "Tip", 6: "Tip"}

    #: Forma de la libreria para el control. Si no existe, create_control_from_lib
    #: cae al circulo por defecto y aqui se gira para que abrace el hueso.
    CONTROL_STYLE = "circleControl"

    #: Giro extra de la forma (en grados, sobre los CVs) por si la de la
    #: libreria no esta dibujada con la normal en X.
    CONTROL_ROTATE = (0, 0, 0)

    #: Radio del control como fraccion de la longitud del segmento.
    CONTROL_RADIUS_RATIO = 0.2

    #: Separacion de la curva offset, como fraccion de la longitud del
    #: segmento. Solo da la direccion del up vector: el valor exacto no
    #: importa mientras no sea casi cero.
    OFFSET_RATIO = 0.25

    #: Sufijo de los joints internos (drivers y bendy). NO acaban en JNT a
    #: proposito: skinning_module se lleva al skin cualquier joint que acabe
    #: en JNT, y estos solo deforman las curvas, no la malla.
    DRIVER_SUFFIX = "DRV"

    #: Los drivers y los joints de salida tienen inheritsTransform a 0 (van en
    #: coordenadas de mundo, como los del twist), asi que no heredan el
    #: Global_Scale por jerarquia. A True se les conecta directamente.
    FOLLOW_GLOBAL_SCALE = True

    #: Atributo de visibilidad de los controles en el settings/switch.
    VIS_ATTR = "Bendies"

    def __init__(self, name, side, twist, root_instance=None, settings_ctrl=None):
        """
        Args:
            name (str): el mismo name que se le paso al TwistModule ("arm",
                "leg"). Los nodos salen como {side}_{name}_upperBendy_...
            twist (TwistModule): ya construido, con create_basic_curve hecho.
            settings_ctrl (str): donde va el atributo de visibilidad de los
                controles. Normalmente el switch_CTRL de la extremidad.
        """
        self.name = name
        self.side = side
        self.twist = twist
        self.root_instance = root_instance
        self.settings_ctrl = settings_ctrl

        self.prefix = f"{side}_{name}"
        self.group_maker = ControlsGroups()

        self.rig_grp = None
        self.controls_grp = None

        # Lo que publica el modulo
        self.segments = {}
        self.controls = []
        self.output_joints = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _unit(axis_index, sign=1.0):
        return tuple(sign if k == axis_index else 0.0 for k in range(3))

    @staticmethod
    def _ws(node):
        return cmds.xform(node, q=True, ws=True, t=True)

    def _distance(self, node_a, node_b):
        a, b = self._ws(node_a), self._ws(node_b)
        return math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))

    @staticmethod
    def _shape(curve):
        return cmds.listRelatives(curve, shapes=True, noIntermediate=True)[0]

    @staticmethod
    def _world_axis(node, axis_index):
        """Eje local 'axis_index' de 'node', en mundo y normalizado."""
        # getAttr y no xform: obliga a evaluar el DG, y los drivers acaban de
        # conectarse a sus motionPath.
        matrix = cmds.getAttr(f"{node}.worldMatrix[0]")
        vec = matrix[axis_index * 4: axis_index * 4 + 3]
        length = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / length for v in vec]

    def _global_scale_plug(self):
        rig_name = getattr(self.root_instance, "rig_name", None) or "Character"
        plug = f"{rig_name}_global_CTL.Global_Scale"
        node, attr = plug.split(".")
        if cmds.objExists(node) and cmds.attributeQuery(attr, node=node, exists=True):
            return plug
        return None

    def _follow_global_scale(self, node):
        if not (self.FOLLOW_GLOBAL_SCALE and self.global_scale):
            return
        for axis in "XYZ":
            cmds.connectAttr(self.global_scale, f"{node}.scale{axis}", force=True)

    def _world_joint(self, name, parent):
        """
        Joint que vive en coordenadas de mundo bajo 'parent'.

        inheritsTransform a 0 ANTES del parent y parent relativo: asi sus
        valores locales se quedan a cero y lo unico que lo mueve son las
        conexiones de los motionPath, que ya salen en mundo.
        """
        cmds.select(clear=True)
        jnt = cmds.joint(n=name)
        cmds.setAttr(f"{jnt}.inheritsTransform", 0)
        jnt = cmds.parent(jnt, parent, relative=True)[0]
        self._follow_global_scale(jnt)
        return jnt

    def _world_transform(self, name, motion_path, parent):
        trn = cmds.createNode("transform", n=name)
        cmds.setAttr(f"{trn}.inheritsTransform", 0)
        trn = cmds.parent(trn, parent, relative=True)[0]
        cmds.connectAttr(f"{motion_path}.allCoordinates", f"{trn}.translate")
        return trn

    def _motion_path(self, curve_shape, u_value, name, tag):
        """motionPath en modo fraccion, solo posicion (sin follow)."""
        mpa = NodeCreator(side=self.side, node_type="motionPath",
                          base_name=self.name, name=name, tag=tag,
                          parent=None, custom_suffix="MPA").create()
        cmds.connectAttr(f"{curve_shape}.worldSpace[0]", f"{mpa}.geometryPath")
        cmds.setAttr(f"{mpa}.fractionMode", True)
        cmds.setAttr(f"{mpa}.follow", False)
        cmds.setAttr(f"{mpa}.uValue", u_value)
        return mpa

    def _bezier(self, name, points, parent):
        """Curva bezier de 7 CVs, en mundo, bajo 'parent'."""
        crv = cmds.curve(d=3, bezier=True, p=points, n=name)
        cmds.setAttr(f"{crv}.inheritsTransform", 0)
        crv = cmds.parent(crv, parent, relative=True)[0]
        shape = cmds.listRelatives(crv, shapes=True)[0]
        cmds.rename(shape, f"{crv}Shape")
        return crv

    # ------------------------------------------------------------------
    # Comprobaciones
    # ------------------------------------------------------------------
    def _twist_ready(self):
        twist = self.twist
        if twist is None:
            cmds.warning(f"[{self.prefix} bendies] No hay twist: las bendies "
                         f"salen de sus motionPath. Activa Twist.")
            return False

        for segment in self.SEGMENTS:
            mpas = getattr(twist, f"{segment}_motion_paths", None) or []
            if len(mpas) < 5:
                cmds.warning(f"[{self.prefix} bendies] El twist tiene "
                             f"{len(mpas)} motionPath en '{segment}' y hacen "
                             f"falta 5. Se saltan las bendies.")
                return False

        for attr in ("start_joint", "mid_joint", "end_joint"):
            node = getattr(twist, attr, None)
            if not node or not cmds.objExists(node):
                cmds.warning(f"[{self.prefix} bendies] Al twist le falta "
                             f"'{attr}'. Se saltan las bendies.")
                return False

        return True

    def _cleanup_previous_build(self):
        """Sin esto, al reconstruir Maya numera los nombres ('..._CTRL1')."""
        for grp in (f"{self.prefix}_bendy_GRP", f"{self.prefix}_bendyControls_GRP"):
            if cmds.objExists(grp):
                cmds.delete(grp)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build(self):
        if not self._twist_ready():
            return None

        self._cleanup_previous_build()
        self.global_scale = self._global_scale_plug()
        if self.FOLLOW_GLOBAL_SCALE and not self.global_scale:
            cmds.warning(f"[{self.prefix} bendies] No encuentro el Global_Scale: "
                         f"los joints de salida no seguiran la escala global.")

        self._create_groups()

        for segment in self.SEGMENTS:
            self.segments[segment] = self._build_segment(segment)

        self._connect_visibility()

        print(f"[{self.prefix} bendies] Construidas: "
              f"{len(self.output_joints)} joints de skin, "
              f"{len(self.controls)} controles.")

        return self.segments

    def _create_groups(self):
        """
        Parte de rig bajo el twist_GRP de la extremidad (al lado de las curvas
        y joints del twist) y controles bajo el local, como los controles L de
        los brazos y piernas.

        Los controles NO van al mirrorBehaviour_GRP: su grupo va por
        parentConstraint al mid DRV, que ya trae la orientacion de cada lado.
        """
        self.rig_grp = cmds.group(em=True, n=f"{self.prefix}_bendy_GRP")
        self.controls_grp = cmds.group(em=True, n=f"{self.prefix}_bendyControls_GRP")

        twist_grp = getattr(self.twist, "twist_GRP", None)
        if twist_grp and cmds.objExists(twist_grp):
            cmds.parent(self.rig_grp, twist_grp)

        local_ctl = getattr(self.root_instance, "localCtl", None)
        if local_ctl and cmds.objExists(local_ctl):
            cmds.parent(self.controls_grp, local_ctl)
        else:
            cmds.warning(f"[{self.prefix} bendies] Sin local control: los "
                         f"controles se quedan en la raiz de la escena.")

    def _segment_info(self, segment):
        twist = self.twist
        if segment == "upper":
            return twist.upper_motion_paths, twist.start_joint, twist.mid_joint
        return twist.lower_motion_paths, twist.mid_joint, twist.end_joint

    def _axes_from(self, motion_path):
        """
        Ejes de aim y up que usa el twist, leidos de su propio motionPath.

        Asi no hay que pasarlos a mano ni pueden desincronizarse: el brazo
        usa X/Z, la pierna X/-Z, y si un dia el caballo pone inverseFront,
        la cadena de aims lo hereda sola.
        """
        front = cmds.getAttr(f"{motion_path}.frontAxis")
        up = cmds.getAttr(f"{motion_path}.upAxis")
        inverse_front = cmds.getAttr(f"{motion_path}.inverseFront")

        aim = self._unit(front, -1.0 if inverse_front else 1.0)
        up_vec = self._unit(up)

        return aim, up_vec, up

    def _build_segment(self, segment):
        mpas, start, end = self._segment_info(segment)
        seg = f"{self.prefix}_{segment}Bendy"          # L_arm_upperBendy
        length = self._distance(start, end)

        seg_grp = cmds.group(em=True, n=f"{seg}Rig_GRP", p=self.rig_grp)

        # ----------------------------------------------------------------
        # 1. ROOT / MID / TIP
        # Tres joints conectados a tres motionPath del twist: posicion
        # (siguen la curvature) y rotacion (llevan su parte de twist).
        # ----------------------------------------------------------------
        drivers = {}
        for role, index in self.DRIVER_INDICES:
            drv = self._world_joint(f"{seg}{role}_{self.DRIVER_SUFFIX}", seg_grp)
            cmds.connectAttr(f"{mpas[index]}.allCoordinates", f"{drv}.translate")
            cmds.connectAttr(f"{mpas[index]}.rotate", f"{drv}.rotate")
            drivers[role] = drv

        aim_vec, up_vec, up_index = self._axes_from(mpas[2])

        # ----------------------------------------------------------------
        # 2. CONTROL
        # ----------------------------------------------------------------
        ctrl = controlsLibrary.create_control_from_lib(self.CONTROL_STYLE, f"{seg}_CTRL")

        lib_radius = controlsLibrary.control_radius(self.CONTROL_STYLE)
        if not lib_radius:
            # Ha caido al circulo por defecto, que tiene la normal en Y y
            # radio 1: se tumba para que la normal vaya por el hueso (X).
            controlsLibrary.transform_shape(ctrl, rotate=(0, 0, 90))
            lib_radius = 1.0
        elif any(self.CONTROL_ROTATE):
            controlsLibrary.transform_shape(ctrl, rotate=self.CONTROL_ROTATE)

        current = lib_radius * controlsLibrary.get_rig_scale()
        if current > 1e-6:
            controlsLibrary.transform_shape(
                ctrl, scale=(length * self.CONTROL_RADIUS_RATIO) / current)

        ctrl_root = self.group_maker.create_rig_hierarchy(
            ctrl, drivers["Mid"], match_rotation=True)
        ctrl_root = cmds.parent(ctrl_root, self.controls_grp)[0]
        cmds.parentConstraint(drivers["Mid"], ctrl_root, mo=True)

        for attr in ("visibility",):
            cmds.setAttr(f"{ctrl}.{attr}", keyable=False, channelBox=False)

        self.controls.append(ctrl)

        # ----------------------------------------------------------------
        # 3. BENDY JOINT
        # ----------------------------------------------------------------
        cmds.select(clear=True)
        bendy_jnt = cmds.joint(n=f"{seg}_{self.DRIVER_SUFFIX}")
        bendy_jnt = cmds.parent(bendy_jnt, seg_grp)[0]
        cmds.matchTransform(bendy_jnt, ctrl, pos=True, rot=True)
        cmds.parentConstraint(ctrl, bendy_jnt, mo=False)
        cmds.scaleConstraint(ctrl, bendy_jnt, mo=False)

        # ----------------------------------------------------------------
        # 4. CURVAS
        #
        # Bendy: bezier de 7 CVs repartidos por la recta del hueso. Es lo
        # mismo que sale de "linear de 2 CVs -> rebuild a 2 spans -> convert
        # to bezier", pero sin pasar por el historial.
        #
        # Offset: la misma curva desplazada por el eje UP del mid DRV. El PDF
        # la saca con un offsetCurve de normal (0,0,1) en mundo; aqui se
        # desplaza por el eje del propio twist para que funcione igual en un
        # brazo (horizontal) que en una pierna (vertical), y para que los
        # joints de salida queden con la misma orientacion que tendrian los
        # del twist. El offsetCurve del PDF lee de la ShapeOrig, o sea que
        # tampoco era vivo: el resultado es el mismo.
        # ----------------------------------------------------------------
        p0, p1 = self._ws(start), self._ws(end)
        points = [[p0[k] + (p1[k] - p0[k]) * (i / 6.0) for k in range(3)]
                  for i in range(7)]

        up_world = self._world_axis(drivers["Mid"], up_index)
        offset = [v * length * self.OFFSET_RATIO for v in up_world]
        offset_points = [[p[k] + offset[k] for k in range(3)] for p in points]

        curve = self._bezier(f"{seg}_CRV", points, seg_grp)
        offset_curve = self._bezier(f"{seg}Offset_CRV", offset_points, seg_grp)

        influences = {"Root": drivers["Root"], "Bendy": bendy_jnt, "Tip": drivers["Tip"]}
        for crv in (curve, offset_curve):
            self._skin_curve(crv, influences)

        # La curva se ve como template (referencia, no seleccionable); la
        # offset solo da direcciones y se esconde.
        cmds.setAttr(f"{curve}.overrideEnabled", 1)
        cmds.setAttr(f"{curve}.overrideDisplayType", 1)
        cmds.setAttr(f"{offset_curve}.visibility", 0)

        # ----------------------------------------------------------------
        # 5. JOINTS DE SALIDA
        # ----------------------------------------------------------------
        joints, ups, aim_end = self._build_outputs(
            seg, segment, curve, offset_curve, aim_vec, up_vec, seg_grp)

        self.output_joints.extend(joints)

        return {
            "control": ctrl,
            "control_root": ctrl_root,
            "drivers": drivers,
            "bendy_joint": bendy_jnt,
            "curve": curve,
            "offset_curve": offset_curve,
            "joints": joints,
            "up_transforms": ups,
            "aim_end": aim_end,
        }

    def _skin_curve(self, curve, influences):
        """skinCluster con los pesos de CV_WEIGHTS: cada CV al 100% a uno."""
        joints = list(influences.values())
        skin = cmds.skinCluster(*(joints + [curve]), toSelectedBones=True,
                                name=curve.replace("_CRV", "_SKN"))[0]

        for cv, role in self.CV_WEIGHTS.items():
            target = influences[role]
            cmds.skinPercent(skin, f"{curve}.cv[{cv}]",
                             transformValue=[(jnt, 1.0 if jnt == target else 0.0)
                                             for jnt in joints])
        return skin

    def _build_outputs(self, seg, segment, curve, offset_curve, aim_vec, up_vec, parent):
        """
        Cinco joints por la curva bendy y cinco TRN por la offset, en los
        mismos u. Cada joint apunta al siguiente con su TRN como up object.

        El ultimo no tiene siguiente: apunta HACIA ATRAS (aim invertido) a un
        TRN extra que va en el u del penultimo.
        """
        curve_shape = self._shape(curve)
        offset_shape = self._shape(offset_curve)

        # Mismo reparto que el twist: nunca 0 ni 1 exactos.
        count = self.NUM_JOINTS
        u_values = [0.01 + (i / float(count - 1)) * 0.98 for i in range(count)]

        joints, ups, joint_mpas = [], [], []
        for i, u_value in enumerate(u_values):
            mpa = self._motion_path(curve_shape, u_value, f"{segment}Bendy", "joint")
            joint_mpas.append(mpa)

            jnt = self._world_joint(f"{seg}_{i + 1:02d}_JNT", parent)
            cmds.connectAttr(f"{mpa}.allCoordinates", f"{jnt}.translate")
            joints.append(jnt)

            up_mpa = self._motion_path(offset_shape, u_value, f"{segment}BendyUp", "up")
            ups.append(self._world_transform(f"{seg}Up_{i + 1:02d}_TRN", up_mpa, parent))

        aim_end = self._world_transform(f"{seg}AimEnd_TRN", joint_mpas[-2], parent)

        for i in range(count - 1):
            cmds.aimConstraint(joints[i + 1], joints[i], mo=False,
                               aimVector=aim_vec, upVector=up_vec,
                               worldUpType="object", worldUpObject=ups[i])

        back_aim = tuple(-v for v in aim_vec)
        cmds.aimConstraint(aim_end, joints[-1], mo=False,
                           aimVector=back_aim, upVector=up_vec,
                           worldUpType="object", worldUpObject=ups[-1])

        return joints, ups, aim_end

    def _connect_visibility(self):
        ctrl = self.settings_ctrl
        if not ctrl or not cmds.objExists(ctrl):
            return

        if not cmds.attributeQuery(self.VIS_ATTR, node=ctrl, exists=True):
            cmds.addAttr(ctrl, ln=self.VIS_ATTR, at="bool", dv=1)
            cmds.setAttr(f"{ctrl}.{self.VIS_ATTR}", channelBox=True)

        cmds.connectAttr(f"{ctrl}.{self.VIS_ATTR}",
                         f"{self.controls_grp}.visibility", force=True)