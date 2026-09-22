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
    Coll del caball amb RIBBON (NURBS + uvPin).

    Guies (guides_module.HorseNeckGuides): neck_root -> neck_mid -> neck_end

    Build:
      1. NURBS que ocupa tota la guia:
            U = amplada del ribbon, 2 patches (grau 1)
            V = llargada del coll, 10 patches (grau 3)
      2. 3 joints driver (base, mig, final) que fan skin a la NURBS.
      3. 3 controls en jerarquia  neckBase > neckMid > neckEnd,
         cadascun amb parentConstraint al seu driver.
      4. Un uvPin amb 11 coordenades (u = 0.5, v = 0, 0.1 ... 1): una per cada
         interseccio del centre de la NURBS amb les isoparms de V.
         Cada outputMatrix va a l offsetParentMatrix d un joint de sortida.

         control -> driver joint -> skinCluster -> NURBS -> uvPin -> joints

    Els 11 joints de sortida son els de skin i no estan en jerarquia:
    cadascun va enganxat a la superficie (un rivet sobre un ribbon).
    """

    def __init__(self,
                 root_guide="neck_root",
                 mid_guide="neck_mid",
                 end_guide="neck_end",
                 rig_name="Character",
                 v_patches=10,
                 u_patches=2,
                 width=None,
                 parent_joint=None,
                 root_instance=None,
                 skin_weights=[
                [(0.9999, 0.0000, 0.0001), (0.9999, 0.0000, 0.0001), (0.9999, 0.0000, 0.0001)],   # fila V 0
                [(0.8381, 0.1614, 0.0005), (0.8382, 0.1614, 0.0004), (0.8381, 0.1614, 0.0005)],   # fila V 1
                [(0.6755, 0.3221, 0.0024), (0.6757, 0.3222, 0.0021), (0.6755, 0.3221, 0.0024)],   # fila V 2
                [(0.5112, 0.4801, 0.0087), (0.5116, 0.4805, 0.0079), (0.5112, 0.4801, 0.0087)],   # fila V 3
                [(0.3452, 0.6471, 0.0077), (0.3458, 0.6500, 0.0042), (0.3452, 0.6293, 0.0255)],   # fila V 4
                [(0.1810, 0.7576, 0.0614), (0.1814, 0.7594, 0.0592), (0.1810, 0.7576, 0.0614)],   # fila V 5
                [(0.0275, 0.8235, 0.1490), (0.0275, 0.8247, 0.1478), (0.0275, 0.8253, 0.1473)],   # fila V 6
                [(0.0000, 0.7500, 0.2500), (0.0000, 0.7491, 0.2509), (0.0000, 0.7505, 0.2495)],   # fila V 7
                [(0.0000, 0.6496, 0.3504), (0.0000, 0.6426, 0.3574), (0.0000, 0.6450, 0.3550)],   # fila V 8
                [(0.0000, 0.5182, 0.4818), (0.0000, 0.5180, 0.4820), (0.0000, 0.5186, 0.4814)],   # fila V 9
                [(0.0000, 0.3867, 0.6133), (0.0000, 0.3844, 0.6156), (0.0000, 0.3867, 0.6133)],   # fila V 10
                [(0.0000, 0.2851, 0.7149), (0.0000, 0.2811, 0.7189), (0.0000, 0.2851, 0.7149)],   # fila V 11
                [(0.0000, 0.1586, 0.8414), (0.0000, 0.1555, 0.8445), (0.0000, 0.1586, 0.8414)],   # fila V 12
                ]):
        self.guides = [root_guide, mid_guide, end_guide]
        self.rig_name = rig_name
        self.v_patches = v_patches
        self.u_patches = u_patches
        self.width = width            # None -> 10% de la llargada del coll
        self.parent_joint = parent_joint
        self.root_instance = root_instance
        # Pesos a ma: el parametre te prioritat sobre NECK_SKIN_WEIGHTS
        self.skin_weights = skin_weights if skin_weights is not None else NECK_SKIN_WEIGHTS

        self.ctrl_style = "circleControl"
        self.group_maker = ControlsGroups()

        self.surface = None
        self.drivers = []
        self.controls = []
        self.joints = []
        self.uv_pin = None

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

        # U: 2 patches grau 1 | V: 10 patches grau 3 | rang 0-1 en tots dos
        cmds.rebuildSurface(surf, ch=False, rpo=True, rt=0, end=1, kr=0,
                            kcp=False, kc=False,
                            su=self.u_patches, du=1,
                            sv=self.v_patches, dv=3,
                            tol=0.01, fr=0, dir=2)

        self.surface = cmds.parent(surf, parent)[0]
        return self.surface, seg_a / (seg_a + seg_b)

    # ------------------------------------------------------------------ #
    # 2. DRIVERS + SKIN
    # ------------------------------------------------------------------ #
    def _build_drivers(self, guide_pos, parent):
        n = self.rig_name
        names = ["neckBase", "neckMid", "neckEnd"]

        # Cadena temporal per orientar-los al llarg del coll; despres se separen
        cmds.select(clear=True)
        chain = [cmds.joint(p=p, n=f"{n}_{name}_DRV") for name, p in zip(names, guide_pos)]
        cmds.joint(chain[0], e=True, oj="xyz", sao="yup", ch=True, zso=True)
        cmds.setAttr(f"{chain[-1]}.jointOrient", 0, 0, 0)
        cmds.select(clear=True)

        self.drivers = []
        for jnt in reversed(chain):
            self.drivers.insert(0, cmds.parent(jnt, parent)[0])
        for drv in self.drivers:
            cmds.setAttr(f"{drv}.drawStyle", 2)   # amagats
        return self.drivers

    def _skin_surface(self, mid_ratio):
        n = self.rig_name
        skin = cmds.skinCluster(self.drivers, self.surface, tsb=True, mi=2,
                                n=f"{n}_neckRibbon_SKC")[0]
        cmds.setAttr(f"{skin}.normalizeWeights", 0)

        shape = cmds.listRelatives(self.surface, s=True, f=True)[0]
        num_u = cmds.getAttr(f"{shape}.spansU") + cmds.getAttr(f"{shape}.degreeU")
        num_v = cmds.getAttr(f"{shape}.spansV") + cmds.getAttr(f"{shape}.degreeV")

        d0, d1, d2 = self.drivers

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
        for name, drv in zip(names, self.drivers):
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

        for ctrl, drv in zip(self.controls, self.drivers):
            cmds.parentConstraint(ctrl, drv, mo=True, n=f"{drv}_PAC")
        return tops

    # ------------------------------------------------------------------ #
    # 4. UVPIN + JOINTS DE SORTIDA
    # ------------------------------------------------------------------ #
    def _build_output_joints(self, parent):
        n = self.rig_name
        shape = cmds.listRelatives(self.surface, s=True, f=True)[0]

        pin = cmds.createNode("uvPin", n=f"{n}_neckRibbon_UVP")
        cmds.connectAttr(f"{shape}.worldSpace[0]", f"{pin}.deformedGeometry")
        cmds.setAttr(f"{pin}.normalizedIsoParms", 1)
        cmds.setAttr(f"{pin}.normalAxis", 1)    # Y = normal de la NURBS
        cmds.setAttr(f"{pin}.tangentAxis", 2)   # Z = tangent U (amplada)
        self.uv_pin = pin

        self.joints = []
        for i in range(self.v_patches + 1):
            cmds.setAttr(f"{pin}.coordinate[{i}].coordinateU", 0.5)
            cmds.setAttr(f"{pin}.coordinate[{i}].coordinateV", i / float(self.v_patches))

            cmds.select(clear=True)
            jnt = cmds.joint(n=f"{n}_neck_{i + 1:02d}_JNT")
            jnt = cmds.parent(jnt, parent)[0]
            for attr in ("translate", "rotate", "jointOrient"):
                cmds.setAttr(f"{jnt}.{attr}", 0, 0, 0)
            cmds.connectAttr(f"{pin}.outputMatrix[{i}]", f"{jnt}.offsetParentMatrix")
            self.joints.append(jnt)
        cmds.select(clear=True)

        self._fix_pin_axes()
        return self.joints

    def _fix_pin_axes(self):
        """
        Assegura X al llarg del coll (cap al cap) i Y cap amunt.
        Segons el sentit en que ha quedat la NURBS, la normal o la tangent
        poden sortir girades: es comprova amb els dos primers joints.
        """
        pin = self.uv_pin
        _, y, _ = self._world_axes(self.joints[0])
        if self._dot(y, (0, 1, 0)) < 0:
            cmds.setAttr(f"{pin}.normalAxis", 4)   # -Y

        x, _, p0 = self._world_axes(self.joints[0])
        _, _, p1 = self._world_axes(self.joints[1])
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
        self._build_drivers(guide_pos, sys_grp)
        self._skin_surface(mid_ratio)
        tops = self._build_controls(ctrl_grp)
        self._build_output_joints(jnt_grp)

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

        print(f"[HorseNeck] Ribbon construit: NURBS {self.u_patches}x{self.v_patches} patches, "
              f"{len(self.joints)} joints, 3 controls.")
        return self