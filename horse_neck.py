import math
import maya.cmds as cmds
import controlsLibrary
from groups_module import ControlsGroups


# ---------------------------------------------------------------------------
# PESOS DEL SKIN DE LA NURBS (fets a ma i exportats amb export_neck_weights.py)
#
# Una fila per cada fila de CVs al llarg de V (de la base al cap) i, dins de
# cada fila, un tuple per cada CV en U:  (pes base, pes mig, pes final).
# Si es None o no quadra amb la NURBS, es fa servir el repartiment lineal.
# ---------------------------------------------------------------------------
NECK_SKIN_WEIGHTS = None


class HorseNeck(object):
    """
    Coll del caball amb RIBBON (NURBS).

    Guies (guides_module.HorseNeckGuides): neck_root -> neck_mid -> neck_end

    Build:
      1. NURBS que ocupa tota la guia:
            U = amplada, 1 span grau 2   -> 3 CVs (vora, centre, vora)
            V = llargada, 2 spans grau 3 -> 5 CVs
      2. 3 joints (base, mig i final) que deformen la NURBS amb un skinCluster.
         Son els joints de skin del coll.
      3. 3 controls en jerarquia  neckBase > neckMid > neckEnd,
         cadascun amb parentConstraint al seu joint.

         control -> joint -> skinCluster -> NURBS

      4. Cap: un joint i un control al final del coll (head=True), penjat del
         neckEnd_CTRL. El joint del cap es un joint de skin mes.
      5. Opcional (pin_joints > 0): joints extra enganxats a la superficie amb
         un uvPin, repartits per la V. Per defecte no se n creen.
    """

    def __init__(self,
                 root_guide="neck_root",
                 mid_guide="neck_mid",
                 end_guide="neck_end",
                 rig_name="Character",
                 v_spans=2,
                 v_degree=3,
                 u_spans=1,
                 u_degree=2,
                 pin_joints=0,
                 head=True,
                 head_guide=None,
                 width=None,
                 parent_joint=None,
                 root_instance=None,
                 skin_weights=None):
        self.guides = [root_guide, mid_guide, end_guide]
        self.rig_name = rig_name
        self.v_spans = v_spans
        self.v_degree = v_degree
        self.u_spans = u_spans
        self.u_degree = u_degree
        self.pin_joints = pin_joints
        #Cap: joint i control al final del coll. head_guide=None -> la guia
        #del final del coll (neck_end)
        self.head = head
        self.head_guide = head_guide
        self.width = width            # None -> 10% de la llargada del coll
        self.parent_joint = parent_joint
        self.root_instance = root_instance
        # Pesos a ma: el parametre te prioritat sobre NECK_SKIN_WEIGHTS
        self.skin_weights = skin_weights if skin_weights is not None else NECK_SKIN_WEIGHTS

        self.ctrl_style = "circleControl"
        self.group_maker = ControlsGroups()

        self.surface = None
        self.joints = []        # els 3 joints de skin (base, mig, final)
        self.controls = []
        self.pinned = []        # joints extra enganxats amb uvPin (opcional)
        self.uv_pin = None
        self.head_joint = None
        self.head_ctrl = None

    # ------------------------------------------------------------------ #
    # HELPERS
    # ------------------------------------------------------------------ #
    @staticmethod
    def _sub(a, b):
        return [a[i] - b[i] for i in range(3)]

    @staticmethod
    def _dot(a, b):
        return sum(a[i] * b[i] for i in range(3))

    @staticmethod
    def _length(a):
        return math.sqrt(sum(v * v for v in a))

    @staticmethod
    def _world_axes(node):
        m = cmds.xform(node, q=True, ws=True, m=True)
        return m[0:3], m[4:7], m[12:15]   # X, Y, posicio

    # ------------------------------------------------------------------ #
    # 1. NURBS
    # ------------------------------------------------------------------ #
    def _build_surface(self, guide_pos, parent):
        n = self.rig_name
        seg_a = self._length(self._sub(guide_pos[1], guide_pos[0]))
        seg_b = self._length(self._sub(guide_pos[2], guide_pos[1]))
        width = self.width or (seg_a + seg_b) * 0.1

        # Tres corbes paral.leles per les guies (el coll es al pla sagital,
        # l amplada va en X del mon): esquerra, centre, dreta
        curves = []
        for offset in (-width * 0.5, 0.0, width * 0.5):
            pts = [(p[0] + offset, p[1], p[2]) for p in guide_pos]
            curves.append(cmds.curve(ep=pts, d=3))

        surf = cmds.loft(curves, ch=False, u=True, c=False, ar=True, d=1,
                         ss=1, rn=False, po=0, rsn=True,
                         n=f"{n}_neckRibbon_NRB")[0]
        cmds.delete(curves)

        # El loft deixa U al llarg de les corbes: s intercanvien U i V
        # perque U sigui l amplada i V la llargada
        cmds.reverseSurface(surf, d=3, ch=False, rpo=True)

        # U: 1 span grau 2 | V: 2 spans grau 3 | rang 0-1 en tots dos
        cmds.rebuildSurface(surf, ch=False, rpo=True, rt=0, end=1, kr=0,
                            kcp=False, kc=False,
                            su=self.u_spans, du=self.u_degree,
                            sv=self.v_spans, dv=self.v_degree,
                            tol=0.01, fr=0, dir=2)

        self.surface = cmds.parent(surf, parent)[0]
        return self.surface, seg_a / (seg_a + seg_b)

    # ------------------------------------------------------------------ #
    # 2. JOINTS + SKIN
    # ------------------------------------------------------------------ #
    def _build_joints(self, guide_pos, parent):
        """Els 3 joints del coll: deformen la NURBS i son els de skin."""
        n = self.rig_name
        names = ["neckBase", "neckMid", "neckEnd"]

        # Cadena temporal per orientar-los al llarg del coll; despres se separen
        cmds.select(clear=True)
        chain = [cmds.joint(p=p, n=f"{n}_{name}_JNT") for name, p in zip(names, guide_pos)]
        cmds.joint(chain[0], e=True, oj="xyz", sao="yup", ch=True, zso=True)
        cmds.setAttr(f"{chain[-1]}.jointOrient", 0, 0, 0)
        cmds.select(clear=True)

        self.joints = []
        for jnt in reversed(chain):
            self.joints.insert(0, cmds.parent(jnt, parent)[0])
        return self.joints

    def _skin_surface(self, mid_ratio):
        n = self.rig_name
        skin = cmds.skinCluster(self.joints, self.surface, tsb=True, mi=2,
                                n=f"{n}_neckRibbon_SKC")[0]
        cmds.setAttr(f"{skin}.normalizeWeights", 0)

        shape = cmds.listRelatives(self.surface, s=True, f=True)[0]
        num_u = cmds.getAttr(f"{shape}.spansU") + cmds.getAttr(f"{shape}.degreeU")
        num_v = cmds.getAttr(f"{shape}.spansV") + cmds.getAttr(f"{shape}.degreeV")

        d0, d1, d2 = self.joints

        # 1) Pesos fets a ma, si n hi ha i quadren amb la NURBS
        table = self.skin_weights
        if table is not None:
            if len(table) == num_v and all(len(row) == num_u for row in table):
                for v, row in enumerate(table):
                    for u, (w0, w1, w2) in enumerate(row):
                        cmds.skinPercent(skin, f"{self.surface}.cv[{u}][{v}]",
                                         tv=[(d0, w0), (d1, w1), (d2, w2)])
                cmds.setAttr(f"{skin}.normalizeWeights", 1)
                print("[HorseNeck] Pesos del ribbon aplicats des de la taula.")
                return skin
            cmds.warning(f"[HorseNeck] La taula de pesos no quadra amb la NURBS "
                         f"({num_v} files x {num_u} CVs). Es fa servir el lineal.")

        # 2) Per defecte: repartiment lineal per fila de CVs (base -> mig -> final)
        for v in range(num_v):
            t = v / float(num_v - 1)
            if t <= mid_ratio:
                k = t / mid_ratio if mid_ratio > 0 else 1.0
                weights = [(d0, 1.0 - k), (d1, k), (d2, 0.0)]
            else:
                k = (t - mid_ratio) / (1.0 - mid_ratio)
                weights = [(d0, 0.0), (d1, 1.0 - k), (d2, k)]
            for u in range(num_u):
                cmds.skinPercent(skin, f"{self.surface}.cv[{u}][{v}]", tv=weights)

        cmds.setAttr(f"{skin}.normalizeWeights", 1)
        return skin

    # ------------------------------------------------------------------ #
    # 3. CONTROLS
    # ------------------------------------------------------------------ #
    def _build_controls(self, ctrl_grp):
        n = self.rig_name
        names = ["neckBase", "neckMid", "neckEnd"]
        tops = []
        self.controls = []
        for name, drv in zip(names, self.joints):
            ctrl = controlsLibrary.create_control_from_lib(
                lib_name=self.ctrl_style,
                final_name=f"{n}_{name}_CTRL"
            )
            tops.append(self.group_maker.create_rig_hierarchy(ctrl, drv))
            self.controls.append(ctrl)

        # Jerarquia: base > mig > final
        cmds.parent(tops[0], ctrl_grp)
        cmds.parent(tops[1], self.controls[0])
        cmds.parent(tops[2], self.controls[1])

        for ctrl, drv in zip(self.controls, self.joints):
            cmds.parentConstraint(ctrl, drv, mo=True, n=f"{drv}_PAC")
        return tops

    # ------------------------------------------------------------------ #
    # 4. CAP
    # ------------------------------------------------------------------ #
    def _build_head(self, parent_ctrl, jnt_parent):
        """
        Joint i control del cap, al final del coll.

        El control penja del neckEnd_CTRL, aixi que el cap acompanya el coll i
        a sobre es pot orientar a part. El joint es de skin, com els del coll.
        """
        n = self.rig_name
        guide = self.head_guide if self.head_guide else self.guides[-1]
        if not cmds.objExists(guide):
            cmds.warning(f"[HorseNeck] No existeix {guide}: cap no creat.")
            return None

        cmds.select(clear=True)
        head_jnt = cmds.joint(n=f"{n}_head_JNT",
                              p=cmds.xform(guide, q=True, ws=True, t=True))
        cmds.matchTransform(head_jnt, self.joints[-1], pos=False, rot=True)
        cmds.makeIdentity(head_jnt, apply=True, t=0, r=1, s=0, n=0)
        head_jnt = cmds.parent(head_jnt, jnt_parent)[0]
        cmds.select(clear=True)

        head_ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.ctrl_style,
            final_name=f"{n}_head_CTRL"
        )
        top = self.group_maker.create_rig_hierarchy(head_ctrl, head_jnt)
        cmds.parent(top, parent_ctrl)
        cmds.parentConstraint(head_ctrl, head_jnt, mo=True, n=f"{head_jnt}_PAC")

        self.head_joint = head_jnt
        self.head_ctrl = head_ctrl
        return head_ctrl

    # ------------------------------------------------------------------ #
    # 5. UVPIN (opcional)
    # ------------------------------------------------------------------ #
    def _build_pinned_joints(self, parent):
        n = self.rig_name
        shape = cmds.listRelatives(self.surface, s=True, f=True)[0]

        pin = cmds.createNode("uvPin", n=f"{n}_neckRibbon_UVP")
        cmds.connectAttr(f"{shape}.worldSpace[0]", f"{pin}.deformedGeometry")
        cmds.setAttr(f"{pin}.normalizedIsoParms", 1)
        cmds.setAttr(f"{pin}.normalAxis", 1)    # Y = normal de la NURBS
        cmds.setAttr(f"{pin}.tangentAxis", 2)   # Z = tangent U (amplada)
        self.uv_pin = pin

        self.pinned = []
        for i in range(self.pin_joints):
            cmds.setAttr(f"{pin}.coordinate[{i}].coordinateU", 0.5)
            cmds.setAttr(f"{pin}.coordinate[{i}].coordinateV",
                         i / float(max(self.pin_joints - 1, 1)))

            cmds.select(clear=True)
            jnt = cmds.joint(n=f"{n}_neckPin_{i + 1:02d}_JNT")
            jnt = cmds.parent(jnt, parent)[0]
            for attr in ("translate", "rotate", "jointOrient"):
                cmds.setAttr(f"{jnt}.{attr}", 0, 0, 0)
            cmds.connectAttr(f"{pin}.outputMatrix[{i}]", f"{jnt}.offsetParentMatrix")
            self.pinned.append(jnt)
        cmds.select(clear=True)

        if len(self.pinned) > 1:
            self._fix_pin_axes()
        return self.pinned

    def _fix_pin_axes(self):
        """
        Assegura X al llarg del coll (cap al cap) i Y cap amunt.
        Segons el sentit en que ha quedat la NURBS, la normal o la tangent
        poden sortir girades: es comprova amb els dos primers joints.
        """
        pin = self.uv_pin
        _, y, _ = self._world_axes(self.pinned[0])
        if self._dot(y, (0, 1, 0)) < 0:
            cmds.setAttr(f"{pin}.normalAxis", 4)   # -Y

        x, _, p0 = self._world_axes(self.pinned[0])
        _, _, p1 = self._world_axes(self.pinned[1])
        if self._dot(x, self._sub(p1, p0)) < 0:
            current = cmds.getAttr(f"{pin}.tangentAxis")
            cmds.setAttr(f"{pin}.tangentAxis", 5 if current == 2 else 2)   # Z <-> -Z

    # ------------------------------------------------------------------ #
    def build(self):
        missing = [g for g in self.guides if not cmds.objExists(g)]
        if missing:
            cmds.error(f"[HorseNeck] Falten guies: {missing}")

        n = self.rig_name
        guide_pos = [cmds.xform(g, q=True, ws=True, t=True) for g in self.guides]

        # Sistemes i joints en espai de mon: no hereten transformacions
        module = cmds.createNode("transform", n=f"{n}_neck_GRP")
        sys_grp = cmds.createNode("transform", n=f"{n}_neckSystems_GRP", parent=module)
        jnt_grp = cmds.createNode("transform", n=f"{n}_neckJoints_GRP", parent=module)
        for grp in (sys_grp, jnt_grp):
            cmds.setAttr(f"{grp}.inheritsTransform", 0)
        cmds.setAttr(f"{sys_grp}.visibility", 0)
        ctrl_grp = cmds.createNode("transform", n=f"{n}_neckControls_GRP")

        _, mid_ratio = self._build_surface(guide_pos, sys_grp)
        self._build_joints(guide_pos, jnt_grp)
        self._skin_surface(mid_ratio)
        tops = self._build_controls(ctrl_grp)
        if self.head:
            self._build_head(self.controls[-1], jnt_grp)
        if self.pin_joints:
            self._build_pinned_joints(jnt_grp)

        # --- Organitzacio -----------------------------------------------------
        rig_grp = f"{self.root_instance.rig_name}_rig_GRP" if self.root_instance else None
        if rig_grp and cmds.objExists(rig_grp):
            cmds.parent(module, rig_grp)

        container = None
        if self.root_instance:
            container = (getattr(self.root_instance, "localCtl", None)
                         or getattr(self.root_instance, "body_ctl", None))
        if container and cmds.objExists(container):
            cmds.parent(ctrl_grp, container)

        # La base del coll segueix el pit de l espina
        if self.parent_joint and cmds.objExists(self.parent_joint):
            cmds.parentConstraint(self.parent_joint, tops[0], mo=True,
                                  n=f"{n}_neckBase_follow_PAC")
        else:
            cmds.warning(f"[HorseNeck] No s ha trobat {self.parent_joint}: "
                         f"el coll no segueix l espina.")

        print(f"[HorseNeck] Ribbon construit: NURBS {self.u_spans}x{self.v_spans} spans "
              f"(grau {self.u_degree}/{self.v_degree}), {len(self.joints)} joints de skin, "
              f"{len(self.pinned)} pinned, 3 controls"
              f"{' + cap' if self.head_ctrl else ''}.")
        return self