# -*- coding: utf-8 -*-
"""
horse_spine.py - Espina dorsal para caballo (Maya 2026, Python 3)

Rig:
  - Guías (locators) de grupa a cruz, editables antes de construir.
  - Cadena de N joints repartidos por longitud de arco (X hacia delante, Y arriba).
  - Spline IK sobre curva skineada a 3 drivers (hip / mid / chest).
  - Advanced Twist con los drivers de hip y chest.
  - FK por encima del IK: COG > fk01 > fk02 > chest.  mid sigue a hip+chest.
  - Stretch con compensación de escala global (atributo en chest_CTRL).
  - pelvis_JNT y chest_JNT fuera de la cadena spline.

Integració amb l autorig (build_module):
  - guide_names: fa servir els joints de guia de CharacterGuides
    (root, spine_lumbar, spine_thoracic, chest) en lloc dels locators propis.
  - root_instance: els joints van a <rig>_rig_GRP i els controls penjen del
    body_CTL (que fa de COG, aixi no es crea un COG duplicat).
  - La mida dels controls s escala segons la llargada real de l espina.
  - attach_control(): fa que chestFix_CTL / localHip_CTL segueixin l espina.

Uso standalone:
    import horse_spine
    spine = horse_spine.HorseSpine(name="spine", num_joints=9)
    spine.build_guides()   # coloca las guías en el caballo
    spine.build()          # construye el rig
"""
import maya.cmds as cmds
import maya.api.OpenMaya as om2


class HorseSpine(object):

    GUIDE_NAMES = ("hip", "lumbar", "thoracic", "chest")
    # Caballo mirando a +Z, en cm (grupa atrás, cruz delante)
    GUIDE_DEFAULTS = (
        (0.0, 150.0, -60.0),
        (0.0, 147.0, -25.0),
        (0.0, 150.0, 15.0),
        (0.0, 158.0, 50.0),
    )
    STACK = ("SPC", "OFF", "SDK")   # GRP > SPC > OFF > SDK > CTRL
    CTRL_SUFFIX = "CTRL"

    def __init__(self, name="spine", num_joints=9, up_vector=(0, 1, 0),
                 guide_names=None, root_instance=None, cog_parent=None):
        if num_joints < 3:
            raise ValueError("num_joints debe ser >= 3")
        if guide_names is not None and len(guide_names) != len(self.GUIDE_NAMES):
            raise ValueError("guide_names necesita %d guias (grupa -> cruz)"
                             % len(self.GUIDE_NAMES))
        self.name = name
        self.num_joints = num_joints
        self.up = om2.MVector(*up_vector)

        #Guies externes (joints de CharacterGuides). Si es None, locators propis.
        self.guide_names = guide_names
        self.root_instance = root_instance

        #Control del que pengen els controls de l espina. Amb root_instance es
        #el body_CTL, que ja fa de COG.
        if cog_parent is None and root_instance is not None:
            cog_parent = getattr(root_instance, "body_ctl", None)
        self.cog_parent = cog_parent

        #Es calcula al build a partir de la llargada de la curva
        self.scale = 1.0

    # ------------------------------------------------------------------ #
    # GUIAS
    # ------------------------------------------------------------------ #
    def build_guides(self):
        grp_name = "%s_guides_GRP" % self.name
        if cmds.objExists(grp_name):
            cmds.warning("Las guías ya existen: %s" % grp_name)
            return grp_name
        grp = cmds.createNode("transform", name=grp_name)
        for g, pos in zip(self.GUIDE_NAMES, self.GUIDE_DEFAULTS):
            loc = cmds.spaceLocator(name="%s_%s_GUIDE" % (self.name, g))[0]
            cmds.setAttr(loc + ".localScale", 5, 5, 5)
            cmds.xform(loc, ws=True, t=pos)
            cmds.parent(loc, grp)
        return grp

    def _guide_positions(self):
        if self.guide_names:
            missing = [g for g in self.guide_names if not cmds.objExists(g)]
            if missing:
                raise RuntimeError("[HorseSpine] Falten guies: %s" % missing)
            return [cmds.xform(g, q=True, ws=True, t=True) for g in self.guide_names]

        positions = []
        for g, default in zip(self.GUIDE_NAMES, self.GUIDE_DEFAULTS):
            node = "%s_%s_GUIDE" % (self.name, g)
            if cmds.objExists(node):
                positions.append(cmds.xform(node, q=True, ws=True, t=True))
            else:
                positions.append(default)
        return positions

    # ------------------------------------------------------------------ #
    # HELPERS
    # ------------------------------------------------------------------ #
    @staticmethod
    def _curve_fn(curve):
        shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
        sel = om2.MSelectionList()
        sel.add(shape)
        return om2.MFnNurbsCurve(sel.getDagPath(0)), shape

    @staticmethod
    def _point_at_length(fn, length):
        total = fn.length()
        if length >= total:
            param = fn.knotDomain[1]
        else:
            param = fn.findParamFromLength(max(length, 0.0))
        p = fn.getPointAtParam(param, om2.MSpace.kWorld)
        t = fn.tangent(param, om2.MSpace.kWorld)
        return om2.MVector(p.x, p.y, p.z), om2.MVector(t)

    def _aim_matrix(self, pos, aim_dir):
        """X = aim, Y = up (ortogonalizado), Z = X ^ Y."""
        x = om2.MVector(aim_dir).normal()
        z = (x ^ self.up).normal()
        y = (z ^ x).normal()
        return [x.x, x.y, x.z, 0.0,
                y.x, y.y, y.z, 0.0,
                z.x, z.y, z.z, 0.0,
                pos.x, pos.y, pos.z, 1.0]

    def _joint(self, name, matrix, parent, radius=2.0):
        cmds.select(clear=True)
        jnt = cmds.joint(name=name, radius=radius * self.scale)
        cmds.xform(jnt, ws=True, m=matrix)
        jnt = cmds.parent(jnt, parent)[0]
        # rotación -> jointOrient
        cmds.makeIdentity(jnt, apply=True, t=False, r=True, s=True, n=False)
        return jnt

    def _ctrl_stack(self, name, pos, parent, radius=15.0,
                    normal=(0, 0, 1), color=17):
        radius *= self.scale
        grp = cmds.createNode("transform", name=name + "_GRP", parent=parent)
        cmds.xform(grp, ws=True, t=[pos.x, pos.y, pos.z])
        stack = {"grp": grp}
        last = grp
        for suf in self.STACK:
            last = cmds.createNode("transform", name="%s_%s" % (name, suf),
                                   parent=last)
            stack[suf.lower()] = last
        ctrl = cmds.circle(name="%s_%s" % (name, self.CTRL_SUFFIX),
                           nr=normal, r=radius, ch=False)[0]
        ctrl = cmds.parent(ctrl, last, relative=True)[0]
        for shp in cmds.listRelatives(ctrl, shapes=True, fullPath=True) or []:
            cmds.setAttr(shp + ".overrideEnabled", 1)
            cmds.setAttr(shp + ".overrideColor", color)
        for attr in ("sx", "sy", "sz", "v"):
            cmds.setAttr("%s.%s" % (ctrl, attr), lock=True, keyable=False,
                         channelBox=False)
        stack["ctrl"] = ctrl
        return stack

    # ------------------------------------------------------------------ #
    # BUILD
    # ------------------------------------------------------------------ #
    def build(self):
        n = self.name
        if cmds.objExists(n + "_module_GRP"):
            raise RuntimeError("Ya existe %s_module_GRP" % n)

        cmds.undoInfo(openChunk=True)
        try:
            return self._build(n)
        finally:
            cmds.undoInfo(closeChunk=True)

    def _build(self, n):
        positions = self._guide_positions()

        # --- Jerarquía del módulo ----------------------------------------
        module = cmds.createNode("transform", name=n + "_module_GRP")
        ctrls_grp = cmds.createNode("transform", name=n + "_controls_GRP", parent=module)
        jnts_grp = cmds.createNode("transform", name=n + "_joints_GRP", parent=module)
        sys_grp = cmds.createNode("transform", name=n + "_systems_GRP", parent=module)
        cmds.setAttr(sys_grp + ".inheritsTransform", 0)
        cmds.setAttr(sys_grp + ".visibility", 0)

        # --- Curva por las guías, reconstruida uniforme ------------------
        crv = cmds.curve(d=3, ep=positions, name=n + "_ik_CRV")
        cmds.rebuildCurve(crv, ch=False, rpo=True, rt=0, end=1, kr=0,
                          kcp=False, kep=True, kt=False, s=4, d=3)
        crv = cmds.parent(crv, sys_grp)[0]
        fn, crv_shape = self._curve_fn(crv)
        total = fn.length()

        #Els radis estan pensats per a una espina de ~110 cm (GUIDE_DEFAULTS).
        #Si l escena te una altra escala, els controls s adapten.
        ref = sum((om2.MVector(*self.GUIDE_DEFAULTS[i + 1]) -
                   om2.MVector(*self.GUIDE_DEFAULTS[i])).length()
                  for i in range(len(self.GUIDE_DEFAULTS) - 1))
        self.scale = total / ref if ref > 0 else 1.0

        # --- Puntos y matrices de la cadena ------------------------------
        pts = []
        for i in range(self.num_joints):
            p, _ = self._point_at_length(fn, total * i / float(self.num_joints - 1))
            pts.append(p)
        mats = []
        for i, p in enumerate(pts):
            aim = (pts[i + 1] - p) if i < len(pts) - 1 else (p - pts[i - 1])
            mats.append(self._aim_matrix(p, aim))

        mid_pos, mid_tan = self._point_at_length(fn, total * 0.5)
        p13, _ = self._point_at_length(fn, total / 3.0)
        p23, _ = self._point_at_length(fn, total * 2.0 / 3.0)

        # --- Joints ------------------------------------------------------
        joints = []
        parent = jnts_grp
        for i, m in enumerate(mats):
            j = self._joint("%s%02d_JNT" % (n, i + 1), m, parent)
            joints.append(j)
            parent = j

        pelvis_jnt = self._joint(n + "_pelvis_JNT", mats[0], jnts_grp, 3.0)
        chest_jnt = self._joint(n + "_chest_JNT", mats[-1], joints[-1], 3.0)

        # --- Controles ---------------------------------------------------
        if self.cog_parent and cmds.objExists(self.cog_parent):
            #El body_CTL de l autorig ja fa de COG: no se n crea un altre
            cog = {"ctrl": ctrls_grp}
        else:
            cog = self._ctrl_stack(n + "_COG", pts[0], ctrls_grp, 45.0, (0, 1, 0), 22)
        hip = self._ctrl_stack(n + "_hip", pts[0], cog["ctrl"], 28.0, (0, 0, 1), 17)
        fk1 = self._ctrl_stack(n + "_fk01", p13, cog["ctrl"], 24.0, (0, 0, 1), 18)
        fk2 = self._ctrl_stack(n + "_fk02", p23, fk1["ctrl"], 24.0, (0, 0, 1), 18)
        chest = self._ctrl_stack(n + "_chest", pts[-1], fk2["ctrl"], 28.0, (0, 0, 1), 17)
        mid = self._ctrl_stack(n + "_mid", mid_pos, cog["ctrl"], 20.0, (0, 0, 1), 20)
        cmds.parentConstraint(hip["ctrl"], chest["ctrl"], mid["spc"], mo=True,
                              name=n + "_mid_SPC_PAC")

        # --- Drivers de la curva -----------------------------------------
        hip_drv = self._joint(n + "_hip_DRV", mats[0], hip["ctrl"], 4.0)
        mid_drv = self._joint(n + "_mid_DRV", self._aim_matrix(mid_pos, mid_tan),
                              mid["ctrl"], 4.0)
        chest_drv = self._joint(n + "_chest_DRV", mats[-1], chest["ctrl"], 4.0)
        for d in (hip_drv, mid_drv, chest_drv):
            cmds.setAttr(d + ".drawStyle", 2)

        skin = cmds.skinCluster([hip_drv, mid_drv, chest_drv], crv, tsb=True,
                                mi=3, name=n + "_ik_SKC")[0]
        cmds.setAttr(skin + ".normalizeWeights", 0)
        num_cvs = cmds.getAttr(crv_shape + ".spans") + cmds.getAttr(crv_shape + ".degree")
        for i in range(num_cvs):
            t = i / float(num_cvs - 1)
            if t <= 0.5:
                w = (1.0 - 2.0 * t, 2.0 * t, 0.0)
            else:
                w = (0.0, 2.0 - 2.0 * t, 2.0 * t - 1.0)
            cmds.skinPercent(skin, "%s.cv[%d]" % (crv, i),
                             tv=[(hip_drv, w[0]), (mid_drv, w[1]), (chest_drv, w[2])])
        cmds.setAttr(skin + ".normalizeWeights", 1)

        # --- Spline IK + Advanced Twist ----------------------------------
        ik = cmds.ikHandle(name=n + "_IKH", sj=joints[0], ee=joints[-1],
                           c=crv_shape, sol="ikSplineSolver",
                           ccv=False, pcv=False)[0]
        cmds.parent(ik, sys_grp)
        cmds.setAttr(ik + ".dTwistControlEnable", 1)
        cmds.setAttr(ik + ".dWorldUpType", 4)        # Object Rotation Up (Start/End)
        cmds.setAttr(ik + ".dForwardAxis", 0)        # +X
        cmds.setAttr(ik + ".dWorldUpAxis", 0)        # +Y
        cmds.setAttr(ik + ".dWorldUpVector", 0, 1, 0, type="double3")
        cmds.setAttr(ik + ".dWorldUpVectorEnd", 0, 1, 0, type="double3")
        cmds.connectAttr(hip_drv + ".worldMatrix[0]", ik + ".dWorldUpMatrix")
        cmds.connectAttr(chest_drv + ".worldMatrix[0]", ik + ".dWorldUpMatrixEnd")

        # --- Stretch con escala global -----------------------------------
        cmds.addAttr(chest["ctrl"], ln="stretch", at="double",
                     min=0, max=1, dv=1, k=True)
        cin = cmds.createNode("curveInfo", name=n + "_ik_CIN")
        cmds.connectAttr(crv_shape + ".worldSpace[0]", cin + ".inputCurve")

        dcm = cmds.createNode("decomposeMatrix", name=n + "_globalScale_DCM")
        cmds.connectAttr(module + ".worldMatrix[0]", dcm + ".inputMatrix")
        rest = cmds.createNode("multDoubleLinear", name=n + "_restLength_MDL")
        cmds.setAttr(rest + ".input1", total)
        cmds.connectAttr(dcm + ".outputScaleX", rest + ".input2")

        ratio = cmds.createNode("multiplyDivide", name=n + "_stretchRatio_MDV")
        cmds.setAttr(ratio + ".operation", 2)
        cmds.connectAttr(cin + ".arcLength", ratio + ".input1X")
        cmds.connectAttr(rest + ".output", ratio + ".input2X")

        bta = cmds.createNode("blendTwoAttr", name=n + "_stretch_BTA")
        cmds.setAttr(bta + ".input[0]", 1.0)
        cmds.connectAttr(ratio + ".outputX", bta + ".input[1]")
        cmds.connectAttr(chest["ctrl"] + ".stretch", bta + ".attributesBlender")

        for j in joints[1:]:
            mdl = cmds.createNode("multDoubleLinear", name=j.replace("_JNT", "_stretch_MDL"))
            cmds.setAttr(mdl + ".input1", cmds.getAttr(j + ".translateX"))
            cmds.connectAttr(bta + ".output", mdl + ".input2")
            cmds.connectAttr(mdl + ".output", j + ".translateX")

        # --- Pelvis y pecho fuera del spline -----------------------------
        cmds.parentConstraint(hip["ctrl"], pelvis_jnt, mo=True, name=n + "_pelvis_PAC")
        cmds.orientConstraint(chest["ctrl"], chest_jnt, mo=True, name=n + "_chest_ORC")

        # --- Integracio amb l autorig -------------------------------------
        if self.root_instance is not None:
            rig_grp = "%s_rig_GRP" % self.root_instance.rig_name
            if cmds.objExists(rig_grp):
                module = cmds.parent(module, rig_grp)[0]
        if self.cog_parent and cmds.objExists(self.cog_parent):
            ctrls_grp = cmds.parent(ctrls_grp, self.cog_parent)[0]

        # --- Limpieza ----------------------------------------------------
        if not self.guide_names:
            guides = n + "_guides_GRP"
            if cmds.objExists(guides):
                cmds.setAttr(guides + ".visibility", 0)
        cmds.select(cog["ctrl"])

        self.data = {
            "module": module, "joints": joints, "pelvis": pelvis_jnt,
            "chest_jnt": chest_jnt, "ik": ik, "curve": crv,
            "controls": {"cog": cog, "hip": hip, "fk01": fk1, "fk02": fk2,
                         "chest": chest, "mid": mid},
        }
        return self.data

    # ------------------------------------------------------------------ #
    # INTEGRACIO
    # ------------------------------------------------------------------ #
    def attach_control(self, driver, ctl, stop_at=None):
        """
        Fa que un control d un altre modul (chestFix_CTL, localHip_CTL...)
        segueixi un control de l espina.

        Es constreny el primer pare del control que tingui translate/rotate
        lliures (sense connexions ni locks), mantenint l offset. Aixi el
        control segueix sent animable i no cal saber com es diuen els grups
        del chest_module o del hip_module.

        Args:
            driver (str): control de l espina (p.ex. data["controls"]["chest"]["ctrl"])
            ctl (str): control a enganxar
            stop_at (str): no pujar mes amunt d aquest node (per defecte el COG)
        """
        stop_at = stop_at or self.cog_parent
        if not cmds.objExists(ctl):
            cmds.warning("[HorseSpine] No existeix %s, no s enganxa." % ctl)
            return None

        attrs = ("tx", "ty", "tz", "rx", "ry", "rz")
        node = ctl
        for _ in range(4):   #nomes els grups d offset propers, mai grups grans
            parents = cmds.listRelatives(node, parent=True)
            if (not parents or parents[0] == stop_at
                    or parents[0].endswith(("_CTL", "_CTRL"))):
                cmds.warning("[HorseSpine] %s no te cap pare lliure per "
                             "constrenyer." % ctl)
                return None
            node = parents[0]
            busy = any(cmds.listConnections("%s.%s" % (node, a), s=True, d=False)
                       or cmds.getAttr("%s.%s" % (node, a), lock=True)
                       for a in attrs)
            if not busy:
                break
        else:
            cmds.warning("[HorseSpine] %s: cap grup d offset lliure a prop." % ctl)
            return None

        cns = cmds.parentConstraint(driver, node, mo=True,
                                    name="%s_follow_PAC" % node)[0]
        print("[HorseSpine] %s segueix %s (via %s)" % (ctl, driver, node))
        return cns


if __name__ == "__main__":
    spine = HorseSpine(name="spine", num_joints=9)
    spine.build_guides()
    # Coloca las guías y después:
    # spine.build()